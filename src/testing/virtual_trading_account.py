#!/usr/bin/env python3
"""
虚拟交易账户管理器
模拟真实交易环境，但不使用真实资金
"""
import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class PositionSide(Enum):
    """持仓方向"""
    LONG = "long"
    SHORT = "short"

@dataclass
class VirtualOrder:
    """虚拟订单"""
    order_id: str
    client_order_id: str
    inst_id: str
    side: str  # buy/sell
    order_type: str  # market/limit
    size: float
    price: float
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    create_time: datetime = None
    update_time: datetime = None
    
    def __post_init__(self):
        if self.create_time is None:
            self.create_time = datetime.now()
        if self.update_time is None:
            self.update_time = self.create_time

@dataclass
class VirtualPosition:
    """虚拟持仓"""
    inst_id: str
    side: PositionSide
    size: float
    avg_price: float
    mark_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin: float = 0.0
    leverage: int = 1
    create_time: datetime = None
    update_time: datetime = None
    
    def __post_init__(self):
        if self.create_time is None:
            self.create_time = datetime.now()
        if self.update_time is None:
            self.update_time = self.create_time

@dataclass
class AccountBalance:
    """账户余额"""
    total_balance: float = 100000.0  # 初始10万USDT
    available_balance: float = 100000.0
    frozen_balance: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_margin: float = 0.0

class VirtualTradingAccount:
    """虚拟交易账户"""
    
    def __init__(self, initial_balance: float = 100000.0, account_name: str = "default"):
        self.account_name = account_name
        self.logger = logging.getLogger(f"{__name__}.{account_name}")
        
        # 账户状态
        self.balance = AccountBalance(
            total_balance=initial_balance,
            available_balance=initial_balance
        )
        
        # 交易记录
        self.orders: Dict[str, VirtualOrder] = {}
        self.positions: Dict[str, VirtualPosition] = {}  # key: inst_id
        self.trade_history: List[Dict] = []
        
        # 配置
        self.maker_fee_rate = 0.0002  # 0.02% maker费率
        self.taker_fee_rate = 0.0005  # 0.05% taker费率
        self.slippage_rate = 0.0001   # 0.01% 模拟滑点
        
        # 统计信息
        self.stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_volume': 0.0,
            'total_fees': 0.0,
            'max_drawdown': 0.0,
            'peak_balance': initial_balance,
            'start_time': datetime.now()
        }
        
        self.logger.info(f"虚拟交易账户创建: {account_name}, 初始余额: ${initial_balance:,.2f}")
    
    def place_order(self, inst_id: str, side: str, order_type: str, size: float, 
                   price: float = None, client_order_id: str = None) -> Dict:
        """下单"""
        try:
            # 生成订单ID
            order_id = f"virtual_{uuid.uuid4().hex[:8]}"
            if client_order_id is None:
                client_order_id = f"client_{int(time.time())}"
            
            # 获取当前市场价格
            current_price = self._get_market_price(inst_id)
            if current_price is None:
                return {
                    'success': False,
                    'error': f'无法获取{inst_id}的市场价格'
                }
            
            # 处理市价单
            if order_type.lower() == 'market':
                price = current_price
            
            # 检查余额
            required_margin = self._calculate_required_margin(inst_id, size, price)
            if required_margin > self.balance.available_balance:
                return {
                    'success': False,
                    'error': f'余额不足，需要${required_margin:,.2f}，可用${self.balance.available_balance:,.2f}'
                }
            
            # 创建订单
            order = VirtualOrder(
                order_id=order_id,
                client_order_id=client_order_id,
                inst_id=inst_id,
                side=side,
                order_type=order_type,
                size=size,
                price=price
            )
            
            # 模拟订单执行
            if order_type.lower() == 'market':
                # 市价单立即成交
                fill_price = self._apply_slippage(current_price, side)
                self._fill_order(order, fill_price, size)
            else:
                # 限价单检查是否能立即成交
                if self._can_fill_immediately(price, current_price, side):
                    fill_price = price
                    self._fill_order(order, fill_price, size)
                else:
                    # 挂单等待
                    order.status = OrderStatus.PENDING
                    self.balance.frozen_balance += required_margin
                    self.balance.available_balance -= required_margin
            
            self.orders[order_id] = order
            
            self.logger.info(f"下单成功: {order_id} {inst_id} {side} {size} @ ${price:.2f}")
            
            return {
                'success': True,
                'order_id': order_id,
                'status': order.status.value
            }
            
        except Exception as e:
            self.logger.error(f"下单失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_market_price(self, inst_id: str) -> Optional[float]:
        """获取市场价格（这里需要连接到真实的价格数据源）"""
        # 这里应该连接到OKX的实时价格API
        # 为了演示，我们使用一些模拟价格
        mock_prices = {
            'BTC-USDT-SWAP': 65000.0,
            'ETH-USDT-SWAP': 3500.0,
            'SOL-USDT-SWAP': 150.0
        }
        
        base_price = mock_prices.get(inst_id)
        if base_price:
            # 添加一些随机波动
            import random
            volatility = base_price * 0.001  # 0.1% 波动
            return base_price + random.uniform(-volatility, volatility)
        
        return None
    
    def _calculate_required_margin(self, inst_id: str, size: float, price: float) -> float:
        """计算所需保证金"""
        # 简化计算，假设10倍杠杆
        leverage = 10
        notional_value = size * price
        return notional_value / leverage
    
    def _apply_slippage(self, price: float, side: str) -> float:
        """应用滑点"""
        slippage = price * self.slippage_rate
        if side.lower() == 'buy':
            return price + slippage
        else:
            return price - slippage
    
    def _can_fill_immediately(self, order_price: float, market_price: float, side: str) -> bool:
        """检查限价单是否能立即成交"""
        if side.lower() == 'buy':
            return order_price >= market_price
        else:
            return order_price <= market_price
    
    def _fill_order(self, order: VirtualOrder, fill_price: float, fill_size: float):
        """成交订单"""
        order.filled_size = fill_size
        order.avg_fill_price = fill_price
        order.status = OrderStatus.FILLED
        order.update_time = datetime.now()
        
        # 计算手续费
        notional_value = fill_size * fill_price
        fee = notional_value * self.taker_fee_rate  # 简化为taker费率
        
        # 更新持仓
        self._update_position(order, fill_price, fill_size, fee)
        
        # 记录交易
        trade_record = {
            'order_id': order.order_id,
            'inst_id': order.inst_id,
            'side': order.side,
            'size': fill_size,
            'price': fill_price,
            'fee': fee,
            'timestamp': order.update_time,
            'pnl': 0.0  # 开仓时PnL为0
        }
        self.trade_history.append(trade_record)
        
        # 更新统计
        self.stats['total_trades'] += 1
        self.stats['total_volume'] += notional_value
        self.stats['total_fees'] += fee
        
        self.logger.info(f"订单成交: {order.order_id} {fill_size} @ ${fill_price:.2f}, 手续费: ${fee:.2f}")
    
    def _update_position(self, order: VirtualOrder, fill_price: float, fill_size: float, fee: float):
        """更新持仓"""
        inst_id = order.inst_id
        
        if inst_id not in self.positions:
            # 新开仓
            side = PositionSide.LONG if order.side.lower() == 'buy' else PositionSide.SHORT
            position = VirtualPosition(
                inst_id=inst_id,
                side=side,
                size=fill_size,
                avg_price=fill_price,
                mark_price=fill_price,
                margin=self._calculate_required_margin(inst_id, fill_size, fill_price)
            )
            self.positions[inst_id] = position
            
            # 更新账户余额
            self.balance.available_balance -= fee
            self.balance.total_margin += position.margin
            
        else:
            # 已有持仓，需要处理加仓或平仓
            position = self.positions[inst_id]
            
            if ((position.side == PositionSide.LONG and order.side.lower() == 'buy') or
                (position.side == PositionSide.SHORT and order.side.lower() == 'sell')):
                # 加仓
                total_cost = position.size * position.avg_price + fill_size * fill_price
                total_size = position.size + fill_size
                position.avg_price = total_cost / total_size
                position.size = total_size
                position.margin += self._calculate_required_margin(inst_id, fill_size, fill_price)
                
            else:
                # 平仓
                close_size = min(fill_size, position.size)
                pnl = self._calculate_pnl(position, fill_price, close_size)
                
                position.size -= close_size
                position.realized_pnl += pnl
                
                # 更新账户余额
                self.balance.realized_pnl += pnl
                self.balance.available_balance += pnl
                
                # 更新交易记录中的PnL
                if self.trade_history:
                    self.trade_history[-1]['pnl'] = pnl
                
                # 更新统计
                if pnl > 0:
                    self.stats['winning_trades'] += 1
                else:
                    self.stats['losing_trades'] += 1
                
                # 如果完全平仓，删除持仓
                if position.size <= 0.001:
                    del self.positions[inst_id]
                
            # 扣除手续费
            self.balance.available_balance -= fee
    
    def _calculate_pnl(self, position: VirtualPosition, close_price: float, close_size: float) -> float:
        """计算平仓盈亏"""
        if position.side == PositionSide.LONG:
            return (close_price - position.avg_price) * close_size
        else:
            return (position.avg_price - close_price) * close_size
    
    def update_mark_prices(self, prices: Dict[str, float]):
        """更新标记价格"""
        total_unrealized_pnl = 0.0
        
        for inst_id, position in self.positions.items():
            if inst_id in prices:
                position.mark_price = prices[inst_id]
                position.unrealized_pnl = self._calculate_pnl(position, position.mark_price, position.size)
                total_unrealized_pnl += position.unrealized_pnl
                position.update_time = datetime.now()
        
        self.balance.unrealized_pnl = total_unrealized_pnl
        
        # 更新最大回撤
        current_equity = self.balance.total_balance + self.balance.realized_pnl + self.balance.unrealized_pnl
        if current_equity > self.stats['peak_balance']:
            self.stats['peak_balance'] = current_equity
        
        drawdown = (self.stats['peak_balance'] - current_equity) / self.stats['peak_balance']
        if drawdown > self.stats['max_drawdown']:
            self.stats['max_drawdown'] = drawdown
    
    def get_account_info(self) -> Dict:
        """获取账户信息"""
        current_equity = self.balance.total_balance + self.balance.realized_pnl + self.balance.unrealized_pnl
        
        return {
            'account_name': self.account_name,
            'balance': asdict(self.balance),
            'current_equity': current_equity,
            'positions_count': len(self.positions),
            'active_orders_count': len([o for o in self.orders.values() if o.status == OrderStatus.PENDING]),
            'statistics': self.stats.copy()
        }
    
    def get_positions(self) -> List[Dict]:
        """获取持仓信息"""
        return [asdict(pos) for pos in self.positions.values()]
    
    def get_orders(self, status: OrderStatus = None) -> List[Dict]:
        """获取订单信息"""
        orders = self.orders.values()
        if status:
            orders = [o for o in orders if o.status == status]
        return [asdict(order) for order in orders]
    
    def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """获取交易历史"""
        return self.trade_history[-limit:]
    
    def save_to_file(self, filename: str):
        """保存账户状态到文件"""
        data = {
            'account_name': self.account_name,
            'balance': asdict(self.balance),
            'positions': {k: asdict(v) for k, v in self.positions.items()},
            'orders': {k: asdict(v) for k, v in self.orders.items()},
            'trade_history': self.trade_history,
            'stats': self.stats,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        self.logger.info(f"账户状态已保存到: {filename}")
    
    def load_from_file(self, filename: str):
        """从文件加载账户状态"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.account_name = data['account_name']
            self.balance = AccountBalance(**data['balance'])
            
            # 恢复持仓
            self.positions = {}
            for k, v in data['positions'].items():
                v['side'] = PositionSide(v['side'])
                v['create_time'] = datetime.fromisoformat(v['create_time'])
                v['update_time'] = datetime.fromisoformat(v['update_time'])
                self.positions[k] = VirtualPosition(**v)
            
            # 恢复订单
            self.orders = {}
            for k, v in data['orders'].items():
                v['status'] = OrderStatus(v['status'])
                v['create_time'] = datetime.fromisoformat(v['create_time'])
                v['update_time'] = datetime.fromisoformat(v['update_time'])
                self.orders[k] = VirtualOrder(**v)
            
            self.trade_history = data['trade_history']
            self.stats = data['stats']
            self.stats['start_time'] = datetime.fromisoformat(self.stats['start_time'])
            
            self.logger.info(f"账户状态已从文件加载: {filename}")
            
        except Exception as e:
            self.logger.error(f"加载账户状态失败: {e}")
            raise

# 全局虚拟账户实例
default_virtual_account = VirtualTradingAccount()
