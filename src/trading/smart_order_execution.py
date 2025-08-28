#!/usr/bin/env python3
"""
智能交易执行器
解决滑点保护、重复下单、部分成交等问题
"""
import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from .trade_executor import OrderParams, OrderResult, TradeExecutor
from ..common.signals import TradingSignal

@dataclass
class SmartOrderResult:
    """智能订单执行结果（扩展版）"""
    success: bool
    order_id: str = ""
    client_order_id: str = ""
    message: str = ""
    filled_size: float = 0.0
    avg_price: float = 0.0
    error_code: str = ""

    @classmethod
    def from_order_result(cls, result: OrderResult, filled_size: float = 0.0, avg_price: float = 0.0):
        """从OrderResult创建SmartOrderResult"""
        return cls(
            success=result.success,
            order_id=result.order_id or "",
            client_order_id=result.client_order_id or "",
            message=result.error_message or ("订单提交成功" if result.success else "订单提交失败"),
            filled_size=filled_size,
            avg_price=avg_price,
            error_code=result.error_code or ""
        )

class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"

class SlippageProtectionMode(Enum):
    """滑点保护模式"""
    NONE = "none"
    PERCENTAGE = "percentage"
    ABSOLUTE = "absolute"
    ADAPTIVE = "adaptive"

@dataclass
class SlippageConfig:
    """滑点配置"""
    mode: SlippageProtectionMode = SlippageProtectionMode.PERCENTAGE
    max_slippage_pct: float = 0.002  # 0.2%最大滑点
    max_slippage_abs: float = 50.0   # $50最大绝对滑点
    adaptive_factor: float = 1.5     # 自适应因子

@dataclass
class OrderTracker:
    """订单跟踪器"""
    order_id: str
    client_order_id: str
    params: OrderParams
    signal: TradingSignal
    submit_time: datetime
    status: OrderStatus = OrderStatus.PENDING
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    slippage: float = 0.0
    retry_count: int = 0
    last_update: datetime = None
    
    def __post_init__(self):
        if self.last_update is None:
            self.last_update = self.submit_time

class SmartOrderExecution:
    """智能交易执行器"""
    
    def __init__(self, base_executor: TradeExecutor):
        self.base_executor = base_executor
        self.logger = logging.getLogger(__name__)
        
        # 配置
        self.slippage_config = SlippageConfig()
        self.max_retry_attempts = 3
        self.retry_delay_seconds = 2.0
        self.duplicate_order_window = 30  # 30秒内防重复下单
        self.partial_fill_timeout = 300   # 5分钟部分成交超时
        
        # 订单跟踪
        self.active_orders: Dict[str, OrderTracker] = {}
        self.recent_orders: List[OrderTracker] = []
        self.order_history_limit = 1000
        
        # 统计信息
        self.stats = {
            'total_orders': 0,
            'successful_orders': 0,
            'failed_orders': 0,
            'cancelled_orders': 0,
            'slippage_protected': 0,
            'duplicate_prevented': 0,
            'partial_fills_handled': 0,
            'retries_executed': 0
        }
    
    def execute_order_smart(self, params: OrderParams, signal: TradingSignal) -> SmartOrderResult:
        """
        智能执行订单
        
        Args:
            params: 订单参数
            signal: 交易信号
            
        Returns:
            订单执行结果
        """
        self.stats['total_orders'] += 1
        
        # 1. 检查重复订单
        if self._check_duplicate_order(params, signal):
            self.stats['duplicate_prevented'] += 1
            return SmartOrderResult(
                success=False,
                order_id="",
                message="防止重复下单",
                filled_size=0.0,
                avg_price=0.0
            )
        
        # 2. 应用滑点保护
        protected_params = self._apply_slippage_protection(params, signal)
        if protected_params != params:
            self.stats['slippage_protected'] += 1
            self.logger.info(f"应用滑点保护: 原价格{params.price} -> 保护价格{protected_params.price}")
        
        # 3. 生成订单跟踪器
        tracker = self._create_order_tracker(protected_params, signal)
        
        # 4. 执行订单（带重试）
        result = self._execute_with_retry(tracker)
        
        # 5. 处理执行结果
        self._handle_execution_result(tracker, result)
        
        return result
    
    def _check_duplicate_order(self, params: OrderParams, signal: TradingSignal) -> bool:
        """检查重复订单"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(seconds=self.duplicate_order_window)
        
        # 检查最近的订单
        for tracker in self.recent_orders:
            if tracker.submit_time < cutoff_time:
                continue
            
            # 检查订单相似性
            if (tracker.params.inst_id == params.inst_id and
                tracker.params.side == params.side and
                abs(tracker.params.size - params.size) < 0.001 and
                tracker.status not in [OrderStatus.FAILED, OrderStatus.CANCELLED]):
                
                self.logger.warning(f"检测到重复订单: {params.inst_id} {params.side.value} {params.size}")
                return True
        
        return False
    
    def _apply_slippage_protection(self, params: OrderParams, signal: TradingSignal) -> OrderParams:
        """应用滑点保护"""
        if self.slippage_config.mode == SlippageProtectionMode.NONE:
            return params
        
        # 获取当前市场价格
        try:
            current_price = self.base_executor.get_current_price(params.inst_id)
        except Exception as e:
            self.logger.warning(f"无法获取当前价格，跳过滑点保护: {e}")
            return params
        
        # 计算滑点保护价格
        protected_price = self._calculate_protected_price(
            params, signal, current_price
        )
        
        if protected_price != params.price:
            # 创建新的参数对象
            protected_params = OrderParams(
                inst_id=params.inst_id,
                side=params.side,
                order_type=params.order_type,
                size=params.size,
                trading_mode=params.trading_mode,
                leverage=params.leverage,
                price=protected_price,
                client_order_id=params.client_order_id,
                reduce_only=params.reduce_only,
                stop_loss=params.stop_loss,
                take_profit=params.take_profit
            )
            return protected_params
        
        return params
    
    def _calculate_protected_price(self, params: OrderParams, signal: TradingSignal, 
                                 current_price: float) -> Optional[float]:
        """计算滑点保护价格"""
        if params.price is None:  # 市价单不需要保护
            return None
        
        expected_price = signal.entry_price
        price_diff = abs(current_price - expected_price)
        
        if self.slippage_config.mode == SlippageProtectionMode.PERCENTAGE:
            max_slippage = expected_price * self.slippage_config.max_slippage_pct
            if price_diff > max_slippage:
                # 调整价格以限制滑点
                if params.side.value.lower() == 'buy':
                    return expected_price + max_slippage
                else:
                    return expected_price - max_slippage
        
        elif self.slippage_config.mode == SlippageProtectionMode.ABSOLUTE:
            if price_diff > self.slippage_config.max_slippage_abs:
                if params.side.value.lower() == 'buy':
                    return expected_price + self.slippage_config.max_slippage_abs
                else:
                    return expected_price - self.slippage_config.max_slippage_abs
        
        elif self.slippage_config.mode == SlippageProtectionMode.ADAPTIVE:
            # 基于信号置信度的自适应滑点
            confidence_factor = signal.confidence
            adaptive_slippage = (expected_price * self.slippage_config.max_slippage_pct * 
                               self.slippage_config.adaptive_factor * (1 - confidence_factor))
            
            if price_diff > adaptive_slippage:
                if params.side.value.lower() == 'buy':
                    return expected_price + adaptive_slippage
                else:
                    return expected_price - adaptive_slippage
        
        return params.price
    
    def _create_order_tracker(self, params: OrderParams, signal: TradingSignal) -> OrderTracker:
        """创建订单跟踪器"""
        client_order_id = params.client_order_id or f"smart_{uuid.uuid4().hex[:8]}"
        
        tracker = OrderTracker(
            order_id="",  # 将在执行后填入
            client_order_id=client_order_id,
            params=params,
            signal=signal,
            submit_time=datetime.now()
        )
        
        return tracker
    
    def _execute_with_retry(self, tracker: OrderTracker) -> SmartOrderResult:
        """带重试的订单执行"""
        last_error = None
        
        for attempt in range(self.max_retry_attempts):
            try:
                tracker.retry_count = attempt
                
                # 执行订单
                result = self.base_executor.place_order(tracker.params)
                
                if result.success:
                    tracker.order_id = result.order_id or ""
                    tracker.status = OrderStatus.SUBMITTED
                    self.logger.info(f"订单提交成功: {result.order_id}")
                    # 从data中提取成交信息
                    filled_size = result.data.get('filled_size', 0.0) if result.data else 0.0
                    avg_price = result.data.get('avg_price', 0.0) if result.data else 0.0
                    return SmartOrderResult.from_order_result(result, filled_size, avg_price)
                else:
                    last_error = result.error_message or "未知错误"
                    self.logger.warning(f"订单执行失败 (尝试 {attempt + 1}): {last_error}")

                    # 检查是否为可重试错误
                    if not self._is_retryable_error(last_error):
                        break
                    
                    if attempt < self.max_retry_attempts - 1:
                        time.sleep(self.retry_delay_seconds * (attempt + 1))
                        self.stats['retries_executed'] += 1
            
            except Exception as e:
                last_error = str(e)
                self.logger.error(f"订单执行异常 (尝试 {attempt + 1}): {e}")
                
                if attempt < self.max_retry_attempts - 1:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))
                    self.stats['retries_executed'] += 1
        
        # 所有重试都失败
        tracker.status = OrderStatus.FAILED
        return SmartOrderResult(
            success=False,
            order_id="",
            message=f"重试{self.max_retry_attempts}次后仍失败: {last_error}",
            filled_size=0.0,
            avg_price=0.0
        )
    
    def _is_retryable_error(self, error_message: str) -> bool:
        """判断错误是否可重试"""
        retryable_patterns = [
            'timeout',
            'network',
            'server error',
            'rate limit',
            'busy',
            'temporary'
        ]
        
        error_lower = error_message.lower()
        return any(pattern in error_lower for pattern in retryable_patterns)
    
    def _handle_execution_result(self, tracker: OrderTracker, result: SmartOrderResult):
        """处理执行结果"""
        tracker.last_update = datetime.now()
        
        if result.success:
            self.stats['successful_orders'] += 1
            tracker.filled_size = result.filled_size
            tracker.avg_fill_price = result.avg_price
            
            # 计算滑点
            if tracker.signal.entry_price > 0:
                tracker.slippage = abs(result.avg_price - tracker.signal.entry_price) / tracker.signal.entry_price
            
            # 检查是否完全成交
            if result.filled_size >= tracker.params.size * 0.99:  # 99%认为完全成交
                tracker.status = OrderStatus.FILLED
            else:
                tracker.status = OrderStatus.PARTIALLY_FILLED
                self.stats['partial_fills_handled'] += 1
                self.logger.warning(f"订单部分成交: {result.filled_size}/{tracker.params.size}")
        else:
            self.stats['failed_orders'] += 1
            tracker.status = OrderStatus.FAILED
        
        # 添加到跟踪列表
        self.active_orders[tracker.order_id] = tracker
        self.recent_orders.append(tracker)
        
        # 限制历史记录大小
        if len(self.recent_orders) > self.order_history_limit:
            self.recent_orders = self.recent_orders[-self.order_history_limit:]
    
    def monitor_active_orders(self) -> List[OrderTracker]:
        """监控活跃订单"""
        updated_orders = []
        current_time = datetime.now()
        
        for order_id, tracker in list(self.active_orders.items()):
            try:
                # 检查订单状态
                order_status = self.base_executor.get_order_status(order_id)
                
                if order_status:
                    # 更新跟踪器状态
                    old_status = tracker.status
                    self._update_tracker_from_status(tracker, order_status)
                    
                    if tracker.status != old_status:
                        updated_orders.append(tracker)
                        self.logger.info(f"订单状态更新: {order_id} {old_status.value} -> {tracker.status.value}")
                
                # 检查部分成交超时
                if (tracker.status == OrderStatus.PARTIALLY_FILLED and
                    (current_time - tracker.submit_time).total_seconds() > self.partial_fill_timeout):
                    
                    self.logger.warning(f"部分成交订单超时，尝试取消: {order_id}")
                    self._cancel_order(tracker)
                
                # 清理已完成的订单
                if tracker.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED]:
                    del self.active_orders[order_id]
            
            except Exception as e:
                self.logger.error(f"监控订单异常: {order_id} - {e}")
        
        return updated_orders
    
    def _update_tracker_from_status(self, tracker: OrderTracker, order_status: Dict):
        """从订单状态更新跟踪器"""
        # 这里需要根据实际的OKX API响应格式来实现
        # 示例实现
        status_map = {
            'live': OrderStatus.SUBMITTED,
            'partially_filled': OrderStatus.PARTIALLY_FILLED,
            'filled': OrderStatus.FILLED,
            'cancelled': OrderStatus.CANCELLED
        }
        
        api_status = order_status.get('state', 'unknown')
        tracker.status = status_map.get(api_status, OrderStatus.PENDING)
        tracker.filled_size = float(order_status.get('fillSz', 0))
        tracker.avg_fill_price = float(order_status.get('avgPx', 0))
        tracker.last_update = datetime.now()
    
    def _cancel_order(self, tracker: OrderTracker) -> bool:
        """取消订单"""
        try:
            result = self.base_executor.cancel_order(tracker.order_id)
            if result:
                tracker.status = OrderStatus.CANCELLED
                self.stats['cancelled_orders'] += 1
                return True
        except Exception as e:
            self.logger.error(f"取消订单失败: {tracker.order_id} - {e}")
        
        return False
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        total_orders = self.stats['total_orders']
        if total_orders == 0:
            return self.stats
        
        return {
            **self.stats,
            'success_rate': (self.stats['successful_orders'] / total_orders) * 100,
            'failure_rate': (self.stats['failed_orders'] / total_orders) * 100,
            'active_orders_count': len(self.active_orders),
            'avg_slippage': self._calculate_average_slippage()
        }
    
    def _calculate_average_slippage(self) -> float:
        """计算平均滑点"""
        slippages = [tracker.slippage for tracker in self.recent_orders 
                    if tracker.slippage > 0 and tracker.status == OrderStatus.FILLED]
        
        if not slippages:
            return 0.0
        
        return sum(slippages) / len(slippages)
    
    def cleanup_old_orders(self, hours: int = 24):
        """清理旧订单记录"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # 清理recent_orders
        self.recent_orders = [
            tracker for tracker in self.recent_orders 
            if tracker.submit_time > cutoff_time
        ]
        
        # 清理active_orders中的旧订单
        old_order_ids = [
            order_id for order_id, tracker in self.active_orders.items()
            if tracker.submit_time < cutoff_time
        ]
        
        for order_id in old_order_ids:
            del self.active_orders[order_id]
        
        self.logger.info(f"清理了{len(old_order_ids)}个旧订单记录")
