#!/usr/bin/env python3
"""
并发监控管理器 - 管理多个交易对的并发监控
"""
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from threading import Lock
import queue
import pandas as pd

from ..data.market_scanner import MarketScanner, TradingPair
from ..strategies.daytime_oscillation import DaytimeOscillationStrategy, StrategyConfig
from ..utils.config import OKXConfig
from ..common.signals import TradingSignal

@dataclass
class MonitorTask:
    """监控任务"""
    symbol: str
    strategy: DaytimeOscillationStrategy
    last_update: float = 0
    last_signal: Optional[TradingSignal] = None
    error_count: int = 0
    is_active: bool = True

@dataclass
class PositionInfo:
    """持仓信息"""
    symbol: str
    size: float
    value: float
    entry_price: float

class ConcurrentMonitor:
    """并发监控管理器"""
    
    def __init__(self, config: OKXConfig, max_workers: int = 8):
        self.config = config
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        
        # 组件
        self.market_scanner = MarketScanner(config)
        self.strategy_config = StrategyConfig()
        
        # 监控任务
        self.monitor_tasks: Dict[str, MonitorTask] = {}
        self.task_lock = Lock()
        
        # 信号队列
        self.signal_queue = queue.Queue()
        
        # 资金管理
        self.total_capital = 100000.0  # 总资金
        self.max_position_ratio = 0.30  # 最大持仓比例30%
        self.current_positions: Dict[str, PositionInfo] = {}
        self.position_lock = Lock()
        
        # AI调用限制
        self.ai_call_queue = asyncio.Queue(maxsize=3)  # 最多3个并发AI调用
        self.ai_call_lock = Lock()
        
        # 性能统计
        self.stats = {
            'total_signals': 0,
            'successful_trades': 0,
            'rejected_trades': 0,
            'ai_calls': 0,
            'errors': 0
        }
        
    def initialize_monitoring(self, pair_count: int = 24) -> bool:
        """初始化监控系统"""
        try:
            self.logger.info(f"🚀 初始化{pair_count}个交易对的并发监控系统...")
            
            # 获取前N个交易对
            trading_pairs = self.market_scanner.get_top_trading_pairs(pair_count)
            
            if not trading_pairs:
                self.logger.error("未获取到任何交易对")
                return False
            
            # 为每个交易对创建监控任务
            with self.task_lock:
                for pair in trading_pairs:
                    try:
                        # 创建独立的策略实例
                        strategy = DaytimeOscillationStrategy(
                            self.config, 
                            self.strategy_config, 
                            pair.symbol
                        )
                        
                        # 创建监控任务
                        task = MonitorTask(
                            symbol=pair.symbol,
                            strategy=strategy,
                            last_update=time.time()
                        )
                        
                        self.monitor_tasks[pair.symbol] = task
                        self.logger.info(f"✅ 创建监控任务: {pair.symbol}")
                        
                    except Exception as e:
                        self.logger.error(f"创建{pair.symbol}监控任务失败: {e}")
            
            self.logger.info(f"🎯 成功初始化{len(self.monitor_tasks)}个监控任务")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化监控系统失败: {e}")
            return False
    
    def start_monitoring(self, update_interval: int = 60):
        """开始并发监控"""
        self.logger.info(f"🔄 开始并发监控，更新间隔: {update_interval}秒")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while True:
                try:
                    # 提交所有监控任务
                    futures = []
                    
                    with self.task_lock:
                        active_tasks = [task for task in self.monitor_tasks.values() if task.is_active]
                    
                    for task in active_tasks:
                        future = executor.submit(self._monitor_single_pair, task)
                        futures.append((future, task.symbol))
                    
                    # 等待所有任务完成
                    completed_count = 0
                    for future, symbol in futures:
                        try:
                            signal = future.result(timeout=30)  # 30秒超时
                            if signal:
                                self._handle_trading_signal(symbol, signal)
                            completed_count += 1
                        except Exception as e:
                            self.logger.error(f"[{symbol}] 监控失败: {e}")
                            # 添加详细的错误追踪
                            import traceback
                            self.logger.debug(f"[{symbol}] 详细错误信息: {traceback.format_exc()}")
                            self._handle_monitor_error(symbol)
                    
                    self.logger.info(f"📊 本轮监控完成: {completed_count}/{len(active_tasks)}个任务")
                    
                    # 处理信号队列
                    self._process_signal_queue()
                    
                    # 等待下一轮
                    time.sleep(update_interval)
                    
                except KeyboardInterrupt:
                    self.logger.info("收到停止信号，正在关闭监控系统...")
                    break
                except Exception as e:
                    self.logger.error(f"监控循环异常: {e}")
                    time.sleep(10)  # 异常后等待10秒再继续
    
    def _monitor_single_pair(self, task: MonitorTask) -> Optional[TradingSignal]:
        """监控单个交易对"""
        try:
            symbol = task.symbol
            strategy = task.strategy
            
            # 获取市场数据
            market_data = self._get_market_data(symbol)
            if not market_data:
                self.logger.warning(f"[{symbol}] 无法获取市场数据，跳过本轮监控")
                return None
            
            current_price = market_data['current_price']
            df = market_data['klines']
            
            # 更新策略的价格历史
            if not df.empty:
                for _, row in df.tail(5).iterrows():  # 使用最近5条数据
                    strategy.update_price_history(
                        float(row['close']), 
                        float(row['volume'])
                    )
            
            # 计算震荡区间
            if (len(strategy.price_history) >= strategy.strategy_config.range_calculation_hours and
                not strategy.current_range):
                strategy.current_range = strategy.calculate_oscillation_range(
                    strategy.price_history
                )
            
            # 生成信号（使用AI调用限制）
            with self.ai_call_lock:
                technical_signal = strategy.get_technical_signal(current_price)
                ai_signal = strategy.get_ai_prediction_signal(current_price)
                kronos_signal = strategy.get_kronos_prediction_signal(current_price)
                
                # AI最终决策
                combined_signal = strategy.combine_signals(
                    technical_signal, ai_signal, kronos_signal
                )
                
                if combined_signal:
                    self.stats['ai_calls'] += 1
            
            # 更新任务状态
            task.last_update = time.time()
            task.last_signal = combined_signal
            task.error_count = 0
            
            return combined_signal
            
        except Exception as e:
            self.logger.error(f"[{task.symbol}] 监控异常: {e}")
            # 添加详细的错误追踪
            import traceback
            self.logger.debug(f"[{task.symbol}] 详细错误信息: {traceback.format_exc()}")
            task.error_count += 1
            self.stats['errors'] += 1
            return None
    
    def _get_market_data(self, symbol: str) -> Optional[Dict]:
        """获取市场数据"""
        try:
            from ..data.okx_fetcher import OKXDataFetcher

            fetcher = OKXDataFetcher(self.config)

            # 获取当前价格
            current_price = fetcher.get_current_price_with_fallback(symbol)
            if not current_price:
                self.logger.warning(f"[{symbol}] 无法获取当前价格")
                return None

            # 验证价格是否合理
            if current_price <= 0:
                self.logger.error(f"[{symbol}] 获取到无效价格: {current_price}")
                return None

            # 获取K线数据
            try:
                df = fetcher.get_historical_klines(
                    instrument=symbol,
                    bar="1H",
                    limit=25,  # 获取25小时数据
                    validate_quality=False
                )
            except Exception as kline_error:
                self.logger.warning(f"[{symbol}] K线数据获取失败: {kline_error}")
                # 即使K线数据获取失败，也可以继续，只是没有历史数据
                df = None

            self.logger.debug(f"[{symbol}] 获取市场数据成功: 价格=${current_price:.8f}, K线{len(df) if df is not None else 0}条")

            return {
                'current_price': current_price,
                'klines': df if df is not None else pd.DataFrame(),
                'timestamp': time.time()
            }

        except Exception as e:
            self.logger.error(f"[{symbol}] 获取市场数据失败: {e}")
            # 添加详细的错误追踪
            import traceback
            self.logger.debug(f"[{symbol}] 市场数据获取详细错误: {traceback.format_exc()}")
            return None
    
    def _handle_trading_signal(self, symbol: str, signal: TradingSignal):
        """处理交易信号"""
        try:
            # 检查资金管理规则
            if not self._check_position_limits(symbol, signal):
                self.logger.info(f"🚫 [{symbol}] 信号被资金管理规则拒绝")
                self.stats['rejected_trades'] += 1
                return
            
            # 将信号加入队列
            self.signal_queue.put((symbol, signal, time.time()))
            self.stats['total_signals'] += 1

            self.logger.info(f"📈 [{symbol}] 生成交易信号: {signal.signal_type.value} "
                           f"(强度:{signal.strength:.2f}, 置信度:{signal.confidence:.2f})")

        except Exception as e:
            self.logger.error(f"[{symbol}] 处理交易信号失败: {e}")
    
    def _check_position_limits(self, symbol: str, signal: TradingSignal) -> bool:
        """检查持仓限制"""
        try:
            with self.position_lock:
                # 计算当前总持仓价值
                total_position_value = sum(pos.value for pos in self.current_positions.values())
                
                # 检查是否超过30%限制
                position_ratio = total_position_value / self.total_capital
                
                if position_ratio >= self.max_position_ratio:
                    self.logger.warning(f"持仓比例已达{position_ratio:.1%}，超过{self.max_position_ratio:.1%}限制")
                    return False
                
                # 计算新仓位大小（简单分配）
                available_capital = self.total_capital * self.max_position_ratio - total_position_value
                max_position_size = available_capital * 0.1  # 单个品种最多占可用资金的10%
                
                if max_position_size < 100:  # 最小100USDT
                    self.logger.warning(f"可用资金不足，剩余: ${available_capital:.2f}")
                    return False
                
                return True
                
        except Exception as e:
            self.logger.error(f"检查持仓限制失败: {e}")
            return False
    
    def _process_signal_queue(self):
        """处理信号队列"""
        processed = 0
        
        while not self.signal_queue.empty() and processed < 5:  # 每轮最多处理5个信号
            try:
                symbol, signal, timestamp = self.signal_queue.get_nowait()
                
                # 这里可以接入真实的交易执行逻辑
                self.logger.info(f"🎯 [{symbol}] 处理交易信号: {signal.signal_type.value} "
                               f"强度:{signal.strength:.2f} 置信度:{signal.confidence:.2f}")

                self.stats['successful_trades'] += 1
                processed += 1
                
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"处理信号队列异常: {e}")
    
    def _handle_monitor_error(self, symbol: str):
        """处理监控错误"""
        with self.task_lock:
            if symbol in self.monitor_tasks:
                task = self.monitor_tasks[symbol]
                task.error_count += 1
                
                # 如果错误次数过多，暂时停用
                if task.error_count >= 5:
                    task.is_active = False
                    self.logger.warning(f"⚠️ {symbol} 错误次数过多，暂时停用")
    
    def get_monitoring_status(self) -> Dict:
        """获取监控状态"""
        with self.task_lock:
            active_count = sum(1 for task in self.monitor_tasks.values() if task.is_active)
            error_count = sum(task.error_count for task in self.monitor_tasks.values())
        
        with self.position_lock:
            total_position_value = sum(pos.value for pos in self.current_positions.values())
            position_ratio = total_position_value / self.total_capital
        
        return {
            'total_pairs': len(self.monitor_tasks),
            'active_pairs': active_count,
            'total_errors': error_count,
            'position_ratio': position_ratio,
            'signal_queue_size': self.signal_queue.qsize(),
            'stats': self.stats.copy()
        }
