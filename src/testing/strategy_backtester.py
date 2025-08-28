#!/usr/bin/env python3
"""
策略回测引擎
用于长期测试策略效果
"""
import logging
import time
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
import pandas as pd
from .virtual_trading_account import VirtualTradingAccount
from ..data.okx_fetcher import OKXDataFetcher
from ..common.signals import TradingSignal
from ..utils.config import OKXConfig

@dataclass
class BacktestConfig:
    """回测配置"""
    instruments: List[str] = None  # 交易品种
    initial_balance: float = 100000.0  # 初始资金
    test_duration_hours: int = 24  # 测试时长（小时）
    price_update_interval: int = 30  # 价格更新间隔（秒）
    strategy_check_interval: int = 60  # 策略检查间隔（秒）
    max_positions: int = 5  # 最大持仓数
    position_size_pct: float = 0.1  # 单次开仓占总资金比例
    stop_loss_pct: float = 0.02  # 止损比例
    take_profit_pct: float = 0.04  # 止盈比例
    
    def __post_init__(self):
        if self.instruments is None:
            self.instruments = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP']

@dataclass
class BacktestResult:
    """回测结果"""
    start_time: datetime
    end_time: datetime
    initial_balance: float
    final_balance: float
    total_return: float
    total_return_pct: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_fees: float

class StrategyBacktester:
    """策略回测引擎"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.logger = logging.getLogger(__name__)
        
        # 初始化组件
        self.okx_config = OKXConfig()
        self.data_fetcher = OKXDataFetcher(self.okx_config)
        self.virtual_account = VirtualTradingAccount(
            initial_balance=self.config.initial_balance,
            account_name=f"backtest_{int(time.time())}"
        )
        
        # 策略函数
        self.strategy_function: Optional[Callable] = None
        
        # 运行状态
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # 数据存储
        self.price_history: Dict[str, List[Dict]] = {}
        self.signal_history: List[Dict] = []
        self.performance_snapshots: List[Dict] = []
        
        # 线程
        self.price_thread: Optional[threading.Thread] = None
        self.strategy_thread: Optional[threading.Thread] = None
        
        self.logger.info(f"策略回测引擎初始化完成")
        self.logger.info(f"测试品种: {self.config.instruments}")
        self.logger.info(f"初始资金: ${self.config.initial_balance:,.2f}")
        self.logger.info(f"测试时长: {self.config.test_duration_hours}小时")
    
    def set_strategy(self, strategy_func: Callable[[str, Dict], Optional[TradingSignal]]):
        """
        设置策略函数
        
        Args:
            strategy_func: 策略函数，接收(instrument, market_data)，返回TradingSignal或None
        """
        self.strategy_function = strategy_func
        self.logger.info("策略函数已设置")
    
    def start_backtest(self):
        """开始回测"""
        if self.strategy_function is None:
            raise ValueError("请先设置策略函数")
        
        if self.is_running:
            self.logger.warning("回测已在运行中")
            return
        
        self.is_running = True
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(hours=self.config.test_duration_hours)
        
        self.logger.info(f"🚀 开始策略回测")
        self.logger.info(f"开始时间: {self.start_time}")
        self.logger.info(f"预计结束时间: {self.end_time}")
        
        # 启动价格更新线程
        self.price_thread = threading.Thread(target=self._price_update_loop, daemon=True)
        self.price_thread.start()
        
        # 启动策略执行线程
        self.strategy_thread = threading.Thread(target=self._strategy_loop, daemon=True)
        self.strategy_thread.start()
        
        # 启动性能监控线程
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("所有线程已启动")
    
    def stop_backtest(self):
        """停止回测"""
        self.is_running = False
        self.logger.info("正在停止回测...")
        
        # 等待线程结束
        if self.price_thread and self.price_thread.is_alive():
            self.price_thread.join(timeout=5)
        
        if self.strategy_thread and self.strategy_thread.is_alive():
            self.strategy_thread.join(timeout=5)
        
        if hasattr(self, 'monitor_thread') and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        self.logger.info("✅ 回测已停止")
    
    def _price_update_loop(self):
        """价格更新循环"""
        self.logger.info("价格更新线程启动")
        
        while self.is_running and datetime.now() < self.end_time:
            try:
                # 获取所有品种的当前价格
                current_prices = {}
                
                for instrument in self.config.instruments:
                    try:
                        price = self.data_fetcher.get_current_price_with_fallback(instrument)
                        if price:
                            current_prices[instrument] = price
                            
                            # 记录价格历史
                            if instrument not in self.price_history:
                                self.price_history[instrument] = []
                            
                            self.price_history[instrument].append({
                                'timestamp': datetime.now(),
                                'price': price
                            })
                            
                            # 限制历史数据长度
                            if len(self.price_history[instrument]) > 1000:
                                self.price_history[instrument] = self.price_history[instrument][-1000:]
                    
                    except Exception as e:
                        self.logger.error(f"获取{instrument}价格失败: {e}")
                
                # 更新虚拟账户的标记价格
                if current_prices:
                    self.virtual_account.update_mark_prices(current_prices)
                
                time.sleep(self.config.price_update_interval)
                
            except Exception as e:
                self.logger.error(f"价格更新循环异常: {e}")
                time.sleep(5)
        
        self.logger.info("价格更新线程结束")
    
    def _strategy_loop(self):
        """策略执行循环"""
        self.logger.info("策略执行线程启动")
        
        while self.is_running and datetime.now() < self.end_time:
            try:
                # 检查每个品种的策略信号
                for instrument in self.config.instruments:
                    try:
                        # 获取市场数据
                        market_data = self._get_market_data(instrument)
                        if not market_data:
                            continue
                        
                        # 调用策略函数
                        signal = self.strategy_function(instrument, market_data)
                        
                        if signal:
                            self.logger.info(f"收到策略信号: {instrument} {signal.signal_type.value}")
                            
                            # 记录信号历史
                            self.signal_history.append({
                                'timestamp': datetime.now(),
                                'instrument': instrument,
                                'signal': signal,
                                'market_data': market_data
                            })
                            
                            # 执行交易
                            self._execute_signal(instrument, signal, market_data)
                    
                    except Exception as e:
                        self.logger.error(f"处理{instrument}策略信号异常: {e}")
                
                time.sleep(self.config.strategy_check_interval)
                
            except Exception as e:
                self.logger.error(f"策略执行循环异常: {e}")
                time.sleep(10)
        
        self.logger.info("策略执行线程结束")
    
    def _monitor_loop(self):
        """性能监控循环"""
        self.logger.info("性能监控线程启动")
        
        while self.is_running and datetime.now() < self.end_time:
            try:
                # 记录性能快照
                account_info = self.virtual_account.get_account_info()
                snapshot = {
                    'timestamp': datetime.now(),
                    'equity': account_info['current_equity'],
                    'balance': account_info['balance'],
                    'positions_count': account_info['positions_count'],
                    'statistics': account_info['statistics']
                }
                self.performance_snapshots.append(snapshot)
                
                # 限制快照数量
                if len(self.performance_snapshots) > 1000:
                    self.performance_snapshots = self.performance_snapshots[-1000:]
                
                # 每10分钟输出一次状态
                if len(self.performance_snapshots) % 20 == 0:  # 假设30秒一次快照
                    self._log_performance_status(account_info)
                
                time.sleep(30)  # 30秒监控一次
                
            except Exception as e:
                self.logger.error(f"性能监控循环异常: {e}")
                time.sleep(30)
        
        self.logger.info("性能监控线程结束")
    
    def _get_market_data(self, instrument: str) -> Optional[Dict]:
        """获取市场数据"""
        try:
            # 获取当前价格
            current_price = self.data_fetcher.get_current_price_with_fallback(instrument)
            if not current_price:
                return None
            
            # 获取历史K线数据（用于技术分析）
            df = self.data_fetcher.get_historical_klines(
                instrument=instrument,
                bar='1m',
                limit=100,
                validate_quality=False
            )
            
            if df.empty:
                return None
            
            return {
                'current_price': current_price,
                'klines': df,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            self.logger.error(f"获取{instrument}市场数据失败: {e}")
            return None
    
    def _execute_signal(self, instrument: str, signal: TradingSignal, market_data: Dict):
        """执行交易信号"""
        try:
            current_price = market_data['current_price']
            
            # 检查是否已有该品种的持仓
            positions = self.virtual_account.get_positions()
            existing_position = None
            for pos in positions:
                if pos['inst_id'] == instrument:
                    existing_position = pos
                    break
            
            # 根据信号类型执行操作
            if signal.signal_type.value == 'buy':
                if existing_position is None:
                    # 开多仓
                    self._open_long_position(instrument, current_price, signal)
                elif existing_position['side'] == 'short':
                    # 平空仓
                    self._close_position(instrument, existing_position, current_price)
            
            elif signal.signal_type.value == 'sell':
                if existing_position is None:
                    # 开空仓
                    self._open_short_position(instrument, current_price, signal)
                elif existing_position['side'] == 'long':
                    # 平多仓
                    self._close_position(instrument, existing_position, current_price)
            
            elif signal.signal_type.value == 'hold':
                # 持有，不执行操作
                pass
            
        except Exception as e:
            self.logger.error(f"执行交易信号失败: {e}")
    
    def _open_long_position(self, instrument: str, price: float, signal: TradingSignal):
        """开多仓"""
        # 检查最大持仓数限制
        if len(self.virtual_account.positions) >= self.config.max_positions:
            self.logger.warning(f"已达到最大持仓数限制: {self.config.max_positions}")
            return
        
        # 计算仓位大小
        account_info = self.virtual_account.get_account_info()
        available_balance = account_info['balance']['available_balance']
        position_value = available_balance * self.config.position_size_pct
        size = position_value / price / 10  # 假设10倍杠杆
        
        # 下单
        result = self.virtual_account.place_order(
            inst_id=instrument,
            side='buy',
            order_type='market',
            size=size
        )
        
        if result['success']:
            self.logger.info(f"开多仓成功: {instrument} {size:.4f} @ ${price:.2f}")
        else:
            self.logger.error(f"开多仓失败: {result['error']}")
    
    def _open_short_position(self, instrument: str, price: float, signal: TradingSignal):
        """开空仓"""
        # 检查最大持仓数限制
        if len(self.virtual_account.positions) >= self.config.max_positions:
            self.logger.warning(f"已达到最大持仓数限制: {self.config.max_positions}")
            return
        
        # 计算仓位大小
        account_info = self.virtual_account.get_account_info()
        available_balance = account_info['balance']['available_balance']
        position_value = available_balance * self.config.position_size_pct
        size = position_value / price / 10  # 假设10倍杠杆
        
        # 下单
        result = self.virtual_account.place_order(
            inst_id=instrument,
            side='sell',
            order_type='market',
            size=size
        )
        
        if result['success']:
            self.logger.info(f"开空仓成功: {instrument} {size:.4f} @ ${price:.2f}")
        else:
            self.logger.error(f"开空仓失败: {result['error']}")
    
    def _close_position(self, instrument: str, position: Dict, price: float):
        """平仓"""
        side = 'sell' if position['side'] == 'long' else 'buy'
        size = position['size']
        
        result = self.virtual_account.place_order(
            inst_id=instrument,
            side=side,
            order_type='market',
            size=size
        )
        
        if result['success']:
            self.logger.info(f"平仓成功: {instrument} {side} {size:.4f} @ ${price:.2f}")
        else:
            self.logger.error(f"平仓失败: {result['error']}")
    
    def _log_performance_status(self, account_info: Dict):
        """记录性能状态"""
        equity = account_info['current_equity']
        initial_balance = self.config.initial_balance
        return_pct = (equity - initial_balance) / initial_balance * 100
        
        stats = account_info['statistics']
        
        self.logger.info("=" * 60)
        self.logger.info("📊 策略回测实时状态")
        self.logger.info(f"当前权益: ${equity:,.2f}")
        self.logger.info(f"总收益率: {return_pct:+.2f}%")
        self.logger.info(f"最大回撤: {stats['max_drawdown']:.2%}")
        self.logger.info(f"总交易次数: {stats['total_trades']}")
        self.logger.info(f"胜率: {stats['winning_trades']}/{stats['total_trades']} = {stats['winning_trades']/max(1,stats['total_trades']):.1%}")
        self.logger.info(f"总手续费: ${stats['total_fees']:.2f}")
        self.logger.info(f"持仓数量: {account_info['positions_count']}")
        self.logger.info("=" * 60)
    
    def get_backtest_result(self) -> BacktestResult:
        """获取回测结果"""
        account_info = self.virtual_account.get_account_info()
        stats = account_info['statistics']
        
        initial_balance = self.config.initial_balance
        final_balance = account_info['current_equity']
        total_return = final_balance - initial_balance
        total_return_pct = total_return / initial_balance * 100
        
        # 计算胜率和盈亏比
        total_trades = stats['total_trades']
        winning_trades = stats['winning_trades']
        losing_trades = stats['losing_trades']
        win_rate = winning_trades / max(1, total_trades) * 100
        
        # 计算平均盈利和亏损
        trade_history = self.virtual_account.get_trade_history()
        wins = [t['pnl'] for t in trade_history if t['pnl'] > 0]
        losses = [t['pnl'] for t in trade_history if t['pnl'] < 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        profit_factor = abs(sum(wins) / sum(losses)) if losses else float('inf')
        
        # 计算夏普比率（简化版）
        if len(self.performance_snapshots) > 1:
            returns = []
            for i in range(1, len(self.performance_snapshots)):
                prev_equity = self.performance_snapshots[i-1]['equity']
                curr_equity = self.performance_snapshots[i]['equity']
                returns.append((curr_equity - prev_equity) / prev_equity)
            
            if returns:
                avg_return = sum(returns) / len(returns)
                return_std = (sum([(r - avg_return) ** 2 for r in returns]) / len(returns)) ** 0.5
                sharpe_ratio = avg_return / return_std if return_std > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        return BacktestResult(
            start_time=self.start_time or datetime.now(),
            end_time=datetime.now(),
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            total_return_pct=total_return_pct,
            max_drawdown=stats['max_drawdown'],
            sharpe_ratio=sharpe_ratio,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            total_fees=stats['total_fees']
        )
    
    def save_results(self, filename_prefix: str = "backtest"):
        """保存回测结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存虚拟账户状态
        account_file = f"{filename_prefix}_account_{timestamp}.json"
        self.virtual_account.save_to_file(account_file)
        
        # 保存回测结果
        result = self.get_backtest_result()
        result_file = f"{filename_prefix}_result_{timestamp}.json"
        
        import json
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result.__dict__, f, indent=2, ensure_ascii=False, default=str)
        
        self.logger.info(f"回测结果已保存:")
        self.logger.info(f"  账户状态: {account_file}")
        self.logger.info(f"  回测结果: {result_file}")
        
        return account_file, result_file
