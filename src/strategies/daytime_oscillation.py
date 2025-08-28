#!/usr/bin/env python3
"""
比特币白天震荡策略
基于8:00-20:00时段波动较小的特点，结合AI预测的短线震荡策略
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

from ..trading.trade_executor import TradeExecutor, OrderParams, OrderSide, OrderType, TradingMode
from ..utils.config import OKXConfig
from ..common.signals import TradingSignal, SignalType
from ..ai.zhipu_predictor import ZhipuAIPredictor, MarketData, AIPrediction
from ..ai.kronos_predictor import KronosPredictor
from ..data.okx_fetcher import OKXDataFetcher


class MarketCondition(Enum):
    """市场状态"""
    NORMAL = "normal"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    NEWS_PERIOD = "news_period"


@dataclass
class OscillationRange:
    """震荡区间"""
    upper_bound: float
    lower_bound: float
    center_price: float
    range_size: float
    last_update: datetime


@dataclass
class StrategyConfig:
    """策略配置"""
    # 时间设置
    trading_start_hour: int = 8
    trading_end_hour: int = 19
    force_close_hour: int = 19
    force_close_minute: int = 30
    
    # 区间设置
    range_calculation_hours: int = 24
    range_shrink_factor: float = 0.6
    entry_threshold: float = 0.1
    breakout_threshold: float = 0.2
    
    # 信号权重
    technical_weight: float = 0.40
    ai_weight: float = 0.35
    kronos_weight: float = 0.25
    
    # 风险控制
    max_position_ratio: float = 0.30
    max_single_trade: float = 0.10
    daily_loss_limit: float = 0.05
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.015
    leverage: int = 10  # 杠杆倍率
    
    # AI过滤
    min_confidence: float = 0.7
    prediction_horizon_hours: int = 4


class DaytimeOscillationStrategy:
    """白天震荡策略"""
    
    def __init__(self, config: OKXConfig, strategy_config: StrategyConfig = None, instrument: str = "BTC-USDT-SWAP"):
        """初始化策略"""
        self.config = config
        self.strategy_config = strategy_config or StrategyConfig()
        self.instrument = instrument  # 添加品种参数
        self.logger = logging.getLogger(__name__)
        
        # 初始化交易执行器
        self.executor = TradeExecutor(config, demo_mode=False)

        # 初始化数据获取器
        try:
            self.data_fetcher = OKXDataFetcher(config)
            self.logger.info("OKX数据获取器初始化成功")
        except Exception as e:
            self.logger.warning(f"OKX数据获取器初始化失败: {e}")
            self.data_fetcher = None

        # 初始化AI预测器
        try:
            self.ai_predictor = ZhipuAIPredictor()
            self.logger.info("智谱AI预测器初始化成功")
        except Exception as e:
            self.logger.warning(f"智谱AI预测器初始化失败: {e}")
            self.ai_predictor = None

        # 初始化Kronos预测器
        try:
            self.kronos_predictor = KronosPredictor()
            self.logger.info("Kronos预测器初始化成功")
        except Exception as e:
            self.logger.warning(f"Kronos预测器初始化失败: {e}")
            self.kronos_predictor = None

        # 策略状态
        self.current_range: Optional[OscillationRange] = None
        self.daily_pnl: float = 0.0
        self.trade_count: int = 0
        self.consecutive_losses: int = 0
        self.is_active: bool = False

        # 历史数据缓存
        self.price_history: List[float] = []
        self.volume_history: List[float] = []

        self.logger.info("白天震荡策略初始化完成")
    
    def is_trading_time(self) -> bool:
        """检查是否在交易时间内"""
        now = datetime.now()
        current_hour = now.hour
        
        return (self.strategy_config.trading_start_hour <= current_hour < 
                self.strategy_config.trading_end_hour)
    
    def is_force_close_time(self) -> bool:
        """检查是否到达强制平仓时间"""
        now = datetime.now()
        force_close_time = now.replace(
            hour=self.strategy_config.force_close_hour,
            minute=self.strategy_config.force_close_minute,
            second=0,
            microsecond=0
        )
        
        return now >= force_close_time
    
    def calculate_oscillation_range(self, prices: List[float]) -> OscillationRange:
        """计算震荡区间"""
        if len(prices) < self.strategy_config.range_calculation_hours:
            raise ValueError("价格数据不足，无法计算震荡区间")
        
        # 使用最近24小时数据
        recent_prices = prices[-self.strategy_config.range_calculation_hours:]
        
        high_24h = max(recent_prices)
        low_24h = min(recent_prices)
        range_24h = high_24h - low_24h
        
        # 白天震荡区间（缩小范围）
        daytime_range = range_24h * self.strategy_config.range_shrink_factor
        center_price = (high_24h + low_24h) / 2
        
        upper_bound = center_price + daytime_range * 0.3
        lower_bound = center_price - daytime_range * 0.3
        
        return OscillationRange(
            upper_bound=upper_bound,
            lower_bound=lower_bound,
            center_price=center_price,
            range_size=daytime_range,
            last_update=datetime.now()
        )
    
    def get_technical_signal(self, current_price: float) -> TradingSignal:
        """获取技术指标信号"""
        if not self.current_range:
            return TradingSignal(SignalType.HOLD, 0.0, 0.0, current_price, reason="无震荡区间")
        
        # 计算价格在区间中的位置
        range_position = (current_price - self.current_range.lower_bound) / self.current_range.range_size
        
        # 接近下沿 - 买入信号
        if range_position < self.strategy_config.entry_threshold:
            return TradingSignal(
                signal_type=SignalType.BUY,
                strength=1.0 - range_position,  # 越接近下沿信号越强
                confidence=0.8,
                entry_price=current_price,
                stop_loss=current_price * (1 - self.strategy_config.stop_loss_pct),
                take_profit=self.current_range.upper_bound * 0.95,  # 接近上沿平仓
                reason=f"接近区间下沿，位置: {range_position:.2%}"
            )
        
        # 接近上沿 - 卖出信号
        elif range_position > (1 - self.strategy_config.entry_threshold):
            return TradingSignal(
                signal_type=SignalType.SELL,
                strength=range_position,  # 越接近上沿信号越强
                confidence=0.8,
                entry_price=current_price,
                stop_loss=current_price * (1 + self.strategy_config.stop_loss_pct),
                take_profit=self.current_range.lower_bound * 1.05,  # 接近下沿平仓
                reason=f"接近区间上沿，位置: {range_position:.2%}"
            )
        
        # 在区间中部 - 持有
        else:
            return TradingSignal(
                SignalType.HOLD, 0.5, 0.5, current_price, 
                reason=f"在区间中部，位置: {range_position:.2%}"
            )
    
    def get_ai_prediction_signal(self, current_price: float) -> TradingSignal:
        """获取AI预测信号"""
        if not self.ai_predictor:
            return TradingSignal(
                SignalType.HOLD, 0.5, 0.5, current_price,
                reason="AI预测器未初始化"
            )

        try:
            # 构建市场数据
            market_data = self._build_market_data(current_price)

            # 获取AI预测
            prediction = self.ai_predictor.predict(
                market_data=market_data,
                price_history=self.price_history[-24:],  # 最近24个价格点
                time_horizon=self.strategy_config.prediction_horizon_hours * 60,
                instrument=self.instrument  # 传入交易对信息
            )

            # 转换为交易信号
            signal = self.ai_predictor.convert_to_trading_signal(prediction, current_price)

            # 记录预测结果
            self.logger.info(f"[{self.instrument}] 智谱AI预测: {self.ai_predictor.get_prediction_summary(prediction)}")

            return signal

        except Exception as e:
            self.logger.error(f"[{self.instrument}] AI预测异常: {e}")
            return TradingSignal(
                SignalType.HOLD, 0.5, 0.5, current_price,
                reason=f"AI预测异常: {str(e)}"
            )

    def _build_market_data(self, current_price: float) -> MarketData:
        """构建市场数据对象"""
        # 从价格历史计算24小时高低点
        if len(self.price_history) >= 24:
            recent_24h = self.price_history[-24:]
            price_24h_high = max(recent_24h)
            price_24h_low = min(recent_24h)
            price_change_24h = current_price - recent_24h[0]
            price_change_pct_24h = price_change_24h / recent_24h[0] if recent_24h[0] > 0 else 0
        else:
            # 如果历史数据不足，使用当前价格的估算值
            price_24h_high = current_price * 1.05
            price_24h_low = current_price * 0.95
            price_change_24h = 0
            price_change_pct_24h = 0

        # 计算成交量（简化处理）
        volume_24h = sum(self.volume_history[-24:]) if len(self.volume_history) >= 24 else 1000000

        return MarketData(
            current_price=current_price,
            price_24h_high=price_24h_high,
            price_24h_low=price_24h_low,
            volume_24h=volume_24h,
            price_change_24h=price_change_24h,
            price_change_pct_24h=price_change_pct_24h,
            timestamp=datetime.now()
        )
    
    def get_kronos_prediction_signal(self, current_price: float) -> TradingSignal:
        """获取Kronos预测信号"""
        if not self.kronos_predictor:
            return TradingSignal(
                SignalType.HOLD, 0.5, 0.5, current_price,
                reason="Kronos预测器未初始化"
            )

        try:
            # 获取最新的Kronos预测（30分钟内有效）
            prediction = self.kronos_predictor.get_latest_prediction(
                instrument=self.instrument,
                max_age_minutes=30
            )

            if not prediction:
                return TradingSignal(
                    SignalType.HOLD, 0.5, 0.5, current_price,
                    reason="无可用的Kronos预测（30分钟内）"
                )

            # 转换为交易信号
            signal = self.kronos_predictor.convert_to_trading_signal(prediction, current_price)

            # 记录预测结果
            self.logger.info(f"[{self.instrument}] Kronos预测: {self.kronos_predictor.get_prediction_summary(prediction)}")

            return signal

        except Exception as e:
            self.logger.error(f"[{self.instrument}] Kronos预测异常: {e}")
            return TradingSignal(
                SignalType.HOLD, 0.5, 0.5, current_price,
                reason=f"Kronos预测异常: {str(e)}"
            )
    
    def combine_signals(self, technical: TradingSignal, ai: TradingSignal,
                       kronos: TradingSignal) -> TradingSignal:
        """
        新的信号综合方式：将技术指标和Kronos预测喂给AI做最终决策
        """
        try:
            # 准备技术分析数据
            technical_analysis = {}
            if technical and technical.signal_type != SignalType.HOLD:
                technical_analysis = {
                    "signal": technical.signal_type.value,
                    "strength": technical.strength,
                    "confidence": technical.confidence,
                    "reasoning": technical.reason,
                    "oscillation_position": self._get_oscillation_position()
                }

            # 准备Kronos预测数据
            kronos_prediction = {}
            if kronos and kronos.signal_type != SignalType.HOLD:
                kronos_prediction = {
                    "signal": kronos.signal_type.value,
                    "strength": kronos.strength,
                    "confidence": kronos.confidence,
                    "reasoning": kronos.reason
                }

            # 获取当前价格
            current_price = technical.entry_price if technical else (
                kronos.entry_price if kronos else 0
            )

            if current_price == 0:
                self.logger.warning("无法获取当前价格，跳过AI决策")
                return TradingSignal(SignalType.HOLD, 0.5, 0.5, 0, reason="无法获取价格")

            # 如果没有有效的技术或Kronos信号，返回HOLD
            if not technical_analysis and not kronos_prediction:
                return TradingSignal(SignalType.HOLD, 0.5, 0.5, current_price, reason="无有效信号")

            # 让AI基于所有信息做最终决策
            final_decision = self._get_ai_final_decision(current_price, technical_analysis, kronos_prediction)

            if final_decision:
                return final_decision
            else:
                return TradingSignal(SignalType.HOLD, 0.5, 0.5, current_price, reason="AI决策为HOLD")

        except Exception as e:
            self.logger.error(f"信号综合失败: {e}")
            return TradingSignal(SignalType.HOLD, 0.5, 0.5, 0, reason=f"综合失败: {e}")

    def _get_ai_final_decision(self, current_price: float, technical_analysis: dict, kronos_prediction: dict):
        """
        让AI基于技术指标和Kronos预测做最终交易决策
        """
        try:
            # 构建给AI的综合分析数据
            analysis_data = {
                "current_price": current_price,
                "technical_analysis": technical_analysis,
                "kronos_prediction": kronos_prediction,
                "oscillation_range": self.current_range,
                "price_history_summary": self._get_price_history_summary()
            }

            # 调用AI进行最终决策
            ai_decision = self.ai_predictor.get_trading_decision(analysis_data, self.instrument)

            if ai_decision and ai_decision.get('action') != 'hold':
                signal_type_map = {
                    'buy': SignalType.BUY,
                    'sell': SignalType.SELL
                }

                signal_type = signal_type_map.get(ai_decision['action'], SignalType.HOLD)
                if signal_type == SignalType.HOLD:
                    return None

                # 创建AI最终决策信号
                final_signal = TradingSignal(
                    signal_type=signal_type,
                    strength=ai_decision.get('strength', 0.7),
                    confidence=ai_decision.get('confidence', 0.6),
                    entry_price=current_price,
                    reason=f"🤖 AI最终决策: {ai_decision.get('reasoning', '综合分析')}"
                )

                self.logger.info(f"[{self.instrument}] 🤖 AI最终决策: {signal_type.value} "
                               f"(强度:{final_signal.strength:.2f}, 置信度:{final_signal.confidence:.2f})")
                self.logger.info(f"[{self.instrument}]    决策理由: {ai_decision.get('reasoning', '无')}")

                return final_signal

            return None

        except Exception as e:
            self.logger.error(f"[{self.instrument}] AI最终决策失败: {e}")
            return None

    def _get_price_history_summary(self):
        """获取价格历史摘要"""
        if len(self.price_history) < 5:
            return None

        try:
            # price_history存储的是数值列表
            recent_prices = self.price_history[-10:]
            recent_volumes = self.volume_history[-10:] if len(self.volume_history) >= 10 else self.volume_history

            if not recent_prices or len(recent_prices) < 2:
                return None

            return {
                "recent_trend": "up" if recent_prices[-1] > recent_prices[0] else "down",
                "volatility": np.std(recent_prices) / np.mean(recent_prices) if np.mean(recent_prices) > 0 else 0,
                "price_change_1h": (recent_prices[-1] - recent_prices[-2]) / recent_prices[-2] if len(recent_prices) > 1 and recent_prices[-2] > 0 else 0,
                "avg_volume": np.mean(recent_volumes) if recent_volumes else 0
            }
        except Exception as e:
            self.logger.error(f"获取价格历史摘要失败: {e}")
            return None

    def _get_oscillation_position(self):
        """获取当前价格在震荡区间中的位置"""
        if not self.current_range:
            return "unknown"

        if not self.price_history:
            return "unknown"

        # price_history存储的是数值，不是字典
        current_price = self.price_history[-1]
        # current_range是OscillationRange对象
        range_lower = self.current_range.lower_bound
        range_upper = self.current_range.upper_bound
        range_mid = self.current_range.center_price

        if current_price <= range_lower:
            return "below_range"
        elif current_price >= range_upper:
            return "above_range"
        elif current_price < range_mid:
            return "lower_half"
        else:
            return "upper_half"

    def check_risk_conditions(self) -> bool:
        """检查风险条件"""
        # 检查日亏损限制
        if self.daily_pnl < -self.strategy_config.daily_loss_limit:
            self.logger.warning(f"达到日亏损限制: {self.daily_pnl:.2%}")
            return False
        
        # 检查连续亏损
        if self.consecutive_losses >= 5:
            self.logger.warning(f"连续亏损次数过多: {self.consecutive_losses}")
            return False
        
        # 检查市场条件
        market_condition = self.check_market_conditions()
        if market_condition != MarketCondition.NORMAL:
            self.logger.warning(f"市场条件异常: {market_condition}")
            return False
        
        return True
    
    def check_market_conditions(self) -> MarketCondition:
        """检查市场条件"""
        # TODO: 实现市场条件检查
        # 检查波动率、流动性、新闻事件等
        return MarketCondition.NORMAL
    
    def calculate_position_size(self, signal: TradingSignal, account_balance: float) -> float:
        """计算仓位大小"""
        # 基础仓位
        base_size = account_balance * self.strategy_config.max_single_trade
        
        # 根据信号强度调整
        adjusted_size = base_size * signal.strength * signal.confidence
        
        # 检查总仓位限制
        current_positions = self.executor.get_positions("BTC-USDT-SWAP")
        current_position_value = sum(abs(pos.size * pos.mark_price) for pos in current_positions)
        current_ratio = current_position_value / account_balance
        
        if current_ratio + (adjusted_size / account_balance) > self.strategy_config.max_position_ratio:
            adjusted_size = (self.strategy_config.max_position_ratio - current_ratio) * account_balance
        
        return max(0, adjusted_size)
    
    def execute_signal(self, signal: TradingSignal) -> bool:
        """执行交易信号"""
        if signal.signal_type == SignalType.HOLD:
            return True
        
        try:
            # 获取账户余额
            balances = self.executor.get_account_balance()
            usdt_balance = balances.get('USDT', 0)
            
            if usdt_balance < 100:  # 最小余额检查
                self.logger.warning("账户余额不足")
                return False
            
            # 计算仓位大小
            position_size = self.calculate_position_size(signal, usdt_balance)
            
            if position_size < 10:  # 最小交易金额
                self.logger.info("计算仓位过小，跳过交易")
                return True
            
            # 构造订单参数
            order_params = OrderParams(
                inst_id="BTC-USDT-SWAP",
                side=OrderSide.BUY if signal.signal_type == SignalType.BUY else OrderSide.SELL,
                order_type=OrderType.MARKET,  # 使用市价单快速成交
                size=position_size / signal.entry_price,  # 转换为合约张数
                trading_mode=TradingMode.ISOLATED,
                leverage=self.strategy_config.leverage,  # 杠杆倍率
                client_order_id=f"daytime_osc_{int(datetime.now().timestamp())}",
                # 添加止盈止损 - 使用OKX服务端执行
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit
            )
            
            # 执行下单
            result = self.executor.place_order(order_params)
            
            if result.success:
                self.logger.info(f"交易执行成功: {signal.signal_type.value} {order_params.size:.4f} BTC")
                self.trade_count += 1
                return True
            else:
                self.logger.error(f"交易执行失败: {result.error_message}")
                return False
                
        except Exception as e:
            self.logger.error(f"执行交易信号异常: {e}")
            return False

    def monitor_positions(self) -> None:
        """
        监控现有持仓
        注意: 这是备用监控，主要依赖OKX服务端的止盈止损
        """
        try:
            positions = self.executor.get_positions("BTC-USDT-SWAP")

            for position in positions:
                current_price = position.mark_price
                entry_price = position.avg_price

                # 计算价格变化百分比
                if position.side == "long":
                    price_change_pct = (current_price - entry_price) / entry_price

                    # 多头止损: 价格下跌超过止损比例
                    if price_change_pct <= -self.strategy_config.stop_loss_pct:
                        self.logger.warning(f"多头持仓触发止损: 入场${entry_price:.2f} 当前${current_price:.2f} "
                                          f"变化{price_change_pct:.2%}")
                        self.close_position(position, "客户端止损")

                    # 多头止盈: 价格上涨超过止盈比例
                    elif price_change_pct >= self.strategy_config.take_profit_pct:
                        self.logger.info(f"多头持仓触发止盈: 入场${entry_price:.2f} 当前${current_price:.2f} "
                                       f"变化{price_change_pct:.2%}")
                        self.close_position(position, "客户端止盈")

                elif position.side == "short":
                    price_change_pct = (entry_price - current_price) / entry_price

                    # 空头止损: 价格上涨超过止损比例
                    if price_change_pct <= -self.strategy_config.stop_loss_pct:
                        self.logger.warning(f"空头持仓触发止损: 入场${entry_price:.2f} 当前${current_price:.2f} "
                                          f"变化{price_change_pct:.2%}")
                        self.close_position(position, "客户端止损")

                    # 空头止盈: 价格下跌超过止盈比例
                    elif price_change_pct >= self.strategy_config.take_profit_pct:
                        self.logger.info(f"空头持仓触发止盈: 入场${entry_price:.2f} 当前${current_price:.2f} "
                                       f"变化{price_change_pct:.2%}")
                        self.close_position(position, "客户端止盈")

        except Exception as e:
            self.logger.error(f"监控持仓异常: {e}")

    def close_position(self, position, reason: str) -> bool:
        """平仓"""
        try:
            result = self.executor.close_position(
                inst_id=position.inst_id,
                side=position.side,
                size=abs(position.size)
            )

            if result.success:
                self.logger.info(f"平仓成功 ({reason}): {position.inst_id} {position.side} {position.size}")

                # 更新统计
                if position.unrealized_pnl < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0

                self.daily_pnl += position.unrealized_pnl
                return True
            else:
                self.logger.error(f"平仓失败: {result.error_message}")
                return False

        except Exception as e:
            self.logger.error(f"平仓异常: {e}")
            return False

    def force_close_all_positions(self) -> None:
        """强制平仓所有持仓"""
        try:
            positions = self.executor.get_positions("BTC-USDT-SWAP")

            for position in positions:
                self.close_position(position, "强制平仓")

            self.logger.info("强制平仓完成")

        except Exception as e:
            self.logger.error(f"强制平仓异常: {e}")

    def update_price_history(self, current_price: float, current_volume: float = 0) -> None:
        """更新价格历史"""
        self.price_history.append(current_price)
        self.volume_history.append(current_volume)

        # 保持最近48小时的数据
        max_history = 48
        if len(self.price_history) > max_history:
            self.price_history = self.price_history[-max_history:]
            self.volume_history = self.volume_history[-max_history:]

    def load_historical_data(self, hours: int = 48) -> bool:
        """从OKX加载历史数据"""
        try:
            if not self.data_fetcher:
                self.logger.warning("数据获取器未初始化，无法加载历史数据")
                return False

            # 获取历史K线数据（1小时K线）
            df = self.data_fetcher.get_historical_klines(
                instrument=self.instrument,  # 使用策略实例的品种
                bar="1H",
                limit=min(hours, 100)  # 限制请求数量
            )

            if df.empty:
                self.logger.warning("未获取到历史数据")
                return False

            # 清空现有历史数据
            self.price_history = []
            self.volume_history = []

            # 添加历史数据
            for _, row in df.iterrows():
                self.price_history.append(float(row['close']))
                self.volume_history.append(float(row['volume']))

            self.logger.info(f"成功加载 {len(self.price_history)} 小时的历史数据")
            self.logger.info(f"价格范围: ${min(self.price_history):,.2f} - ${max(self.price_history):,.2f}")

            return True

        except Exception as e:
            self.logger.error(f"加载历史数据失败: {e}")
            return False

    def get_current_price(self) -> float:
        """获取当前价格（从OKX市场数据获取）"""
        try:
            # 优先从持仓信息获取标记价格
            positions = self.executor.get_positions(self.instrument)
            if positions:
                return positions[0].mark_price

            # 如果没有持仓，从市场数据API获取最新价格
            if self.data_fetcher:
                # 获取最新的1分钟K线数据
                df = self.data_fetcher.get_historical_klines(
                    instrument=self.instrument,  # 使用策略实例的品种
                    bar="1m",
                    limit=1
                )

                if not df.empty:
                    current_price = float(df.iloc[-1]['close'])
                    self.logger.debug(f"[{self.instrument}] 从市场数据获取当前价格: ${current_price:,.2f}")
                    return current_price

            # 如果都失败了，尝试从价格历史获取最后一个价格
            if self.price_history:
                return self.price_history[-1]

            self.logger.warning(f"[{self.instrument}] 无法获取当前价格，所有方法都失败了")
            return 0.0

        except Exception as e:
            self.logger.error(f"[{self.instrument}] 获取当前价格异常: {e}")
            # 返回价格历史中的最后一个价格作为备用
            if self.price_history:
                return self.price_history[-1]
            return 0.0

    def run_strategy_cycle(self) -> None:
        """运行一个策略周期"""
        try:
            # 1. 检查交易时间
            if not self.is_trading_time():
                if self.is_force_close_time():
                    self.force_close_all_positions()
                return

            # 2. 获取当前价格（从OKX真实数据）
            current_price = self.get_current_price()
            if current_price <= 0:
                self.logger.warning("无法获取当前价格，跳过本次周期")
                return

            # 3. 更新价格历史（使用真实价格）
            # 获取当前成交量（如果可能）
            current_volume = 0
            try:
                if self.data_fetcher:
                    df = self.data_fetcher.get_historical_klines(
                        instrument="BTC-USDT-SWAP",
                        bar="1m",
                        limit=1
                    )
                    if not df.empty:
                        current_volume = float(df.iloc[-1]['volume'])
            except Exception as e:
                self.logger.debug(f"获取成交量失败: {e}")

            self.update_price_history(current_price, current_volume)

            # 4. 更新震荡区间（每小时更新一次）
            if (not self.current_range or
                datetime.now() - self.current_range.last_update > timedelta(hours=1)):

                if len(self.price_history) >= self.strategy_config.range_calculation_hours:
                    self.current_range = self.calculate_oscillation_range(self.price_history)
                    self.logger.info(f"更新震荡区间: [{self.current_range.lower_bound:.2f}, {self.current_range.upper_bound:.2f}]")

            # 5. 检查风险条件
            if not self.check_risk_conditions():
                self.logger.warning("风险条件不满足，暂停交易")
                return

            # 6. 监控现有持仓
            self.monitor_positions()

            # 7. 生成交易信号
            technical_signal = self.get_technical_signal(current_price)
            ai_signal = self.get_ai_prediction_signal(current_price)
            kronos_signal = self.get_kronos_prediction_signal(current_price)

            # 8. 综合信号
            combined_signal = self.combine_signals(technical_signal, ai_signal, kronos_signal)

            # 9. 执行交易
            if combined_signal.confidence > self.strategy_config.min_confidence:
                self.execute_signal(combined_signal)
                self.logger.info(f"信号执行: {combined_signal.signal_type.value} "
                               f"强度:{combined_signal.strength:.2f} "
                               f"置信度:{combined_signal.confidence:.2f}")
            else:
                self.logger.debug(f"信号置信度不足: {combined_signal.confidence:.2f}")

        except Exception as e:
            self.logger.error(f"策略周期执行异常: {e}")

    def start_strategy(self) -> None:
        """启动策略"""
        self.logger.info("启动白天震荡策略")
        self.is_active = True

        # 重置日统计
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.consecutive_losses = 0

        # 加载历史数据
        self.logger.info("正在加载历史市场数据...")
        if self.load_historical_data(48):
            self.logger.info("✅ 历史数据加载成功")
        else:
            self.logger.warning("⚠️ 历史数据加载失败，将使用实时数据")

        # 如果有历史数据，计算初始震荡区间
        if len(self.price_history) >= self.strategy_config.range_calculation_hours:
            self.current_range = self.calculate_oscillation_range(self.price_history)
            self.logger.info(f"初始震荡区间: ${self.current_range.lower_bound:,.2f} - ${self.current_range.upper_bound:,.2f}")

        while self.is_active:
            try:
                self.run_strategy_cycle()
                time.sleep(60)  # 每分钟检查一次

            except KeyboardInterrupt:
                self.logger.info("收到停止信号")
                break
            except Exception as e:
                self.logger.error(f"策略运行异常: {e}")
                time.sleep(60)

        # 策略停止时强制平仓
        self.force_close_all_positions()
        self.logger.info("白天震荡策略已停止")

    def stop_strategy(self) -> None:
        """停止策略"""
        self.is_active = False

    def get_strategy_stats(self) -> Dict:
        """获取策略统计信息"""
        # 获取Kronos预测状态
        kronos_available = False
        kronos_latest = None
        if self.kronos_predictor:
            kronos_available = self.kronos_predictor.is_prediction_available(self.instrument)
            if kronos_available:
                kronos_latest = self.kronos_predictor.get_latest_prediction(self.instrument)

        return {
            'daily_pnl': self.daily_pnl,
            'trade_count': self.trade_count,
            'consecutive_losses': self.consecutive_losses,
            'current_range': {
                'upper': self.current_range.upper_bound if self.current_range else 0,
                'lower': self.current_range.lower_bound if self.current_range else 0,
                'center': self.current_range.center_price if self.current_range else 0
            } if self.current_range else None,
            'is_active': self.is_active,
            'is_trading_time': self.is_trading_time(),
            'predictors': {
                'ai_available': self.ai_predictor is not None,
                'kronos_available': kronos_available,
                'kronos_latest': {
                    'trend': kronos_latest.trend_direction.value if kronos_latest else None,
                    'confidence': kronos_latest.confidence if kronos_latest else None,
                    'price_change_pct': kronos_latest.price_change_pct if kronos_latest else None,
                    'age_minutes': (datetime.now() - kronos_latest.timestamp).total_seconds() / 60 if kronos_latest else None
                } if kronos_latest else None
            }
        }
