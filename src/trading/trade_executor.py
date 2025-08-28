#!/usr/bin/env python3
"""
OKX交易执行器
提供统一的交易API接口，封装OKX原生API
"""
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

from okx.api import Trade, Account
from ..utils.config import OKXConfig


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    POST_ONLY = "post_only"
    FOK = "fok"  # Fill or Kill
    IOC = "ioc"  # Immediate or Cancel


class TradingMode(Enum):
    """交易模式"""
    CASH = "cash"           # 现金模式
    CROSS = "cross"         # 全仓模式
    ISOLATED = "isolated"   # 逐仓模式


class OrderStatus(Enum):
    """订单状态"""
    LIVE = "live"                    # 等待成交
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FILLED = "filled"                # 完全成交
    CANCELED = "canceled"            # 已撤销


@dataclass
class OrderParams:
    """下单参数"""
    inst_id: str                    # 产品ID
    side: OrderSide                 # 买卖方向
    order_type: OrderType           # 订单类型
    size: float                     # 数量
    trading_mode: TradingMode       # 交易模式
    leverage: int = 10              # 杠杆倍率（合约交易必需）
    price: Optional[float] = None   # 价格（限价单必填）
    client_order_id: Optional[str] = None  # 客户端订单ID
    reduce_only: bool = False       # 只减仓
    stop_loss: Optional[float] = None      # 止损价格
    take_profit: Optional[float] = None    # 止盈价格


@dataclass
class OrderResult:
    """下单结果"""
    success: bool
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    data: Optional[Dict] = None


@dataclass
class CancelResult:
    """撤单结果"""
    success: bool
    order_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class PositionInfo:
    """持仓信息"""
    inst_id: str
    side: str
    size: float
    avg_price: float
    unrealized_pnl: float
    margin: float
    leverage: int
    mark_price: float


class TradeExecutor:
    """交易执行器"""
    
    def __init__(self, config: OKXConfig, demo_mode: bool = False):
        """
        初始化交易执行器
        
        Args:
            config: OKX配置
            demo_mode: 是否为模拟盘模式
        """
        self.config = config
        self.demo_mode = demo_mode
        self.logger = logging.getLogger(__name__)
        
        # 设置API环境
        flag = '1' if demo_mode else '0'
        
        # 初始化API客户端
        self.trade_api = Trade(
            key=config.api_key,
            secret=config.secret_key,
            passphrase=config.passphrase,
            flag=flag
        )
        
        self.account_api = Account(
            key=config.api_key,
            secret=config.secret_key,
            passphrase=config.passphrase,
            flag=flag
        )
        
        self.logger.info(f"交易执行器初始化完成 - {'模拟盘' if demo_mode else '实盘'}模式")

    def set_leverage(self, inst_id: str, leverage: int, trading_mode: TradingMode) -> bool:
        """
        设置杠杆倍率

        Args:
            inst_id: 产品ID
            leverage: 杠杆倍率
            trading_mode: 交易模式

        Returns:
            是否设置成功
        """
        try:
            api_params = {
                'instId': inst_id,
                'lever': str(leverage),
                'mgnMode': trading_mode.value
            }

            self.logger.info(f"设置杠杆: {inst_id} {leverage}x {trading_mode.value}")

            response = self.account_api.set_leverage(**api_params)

            if response.get('code') == '0':
                self.logger.info(f"杠杆设置成功: {leverage}x")
                return True
            else:
                error_msg = response.get('msg', '未知错误')
                # 如果杠杆已经是目标值，也算成功
                if 'No change in leverage' in error_msg or '杠杆无变化' in error_msg:
                    self.logger.info(f"杠杆已是目标值: {leverage}x")
                    return True
                else:
                    self.logger.error(f"设置杠杆失败: {error_msg}")
                    return False

        except Exception as e:
            self.logger.error(f"设置杠杆异常: {e}")
            return False
    
    def place_order(self, params: OrderParams) -> OrderResult:
        """
        下单
        
        Args:
            params: 下单参数
            
        Returns:
            下单结果
        """
        try:
            # 先设置杠杆倍率（合约交易必需）
            leverage_result = self.set_leverage(params.inst_id, params.leverage, params.trading_mode)
            if not leverage_result:
                self.logger.warning(f"设置杠杆失败，继续下单（可能已设置过）")

            # 构建API参数
            api_params = {
                'instId': params.inst_id,
                'tdMode': params.trading_mode.value,
                'side': params.side.value,
                'ordType': params.order_type.value,
                'sz': str(params.size)
            }
            
            # 添加价格（限价单必需）
            if params.order_type != OrderType.MARKET and params.price:
                api_params['px'] = str(params.price)
            
            # 添加客户端订单ID
            if params.client_order_id:
                api_params['clOrdId'] = params.client_order_id
            
            # 添加只减仓标志
            if params.reduce_only:
                api_params['reduceOnly'] = 'true'
            
            # 添加止损止盈
            if params.stop_loss or params.take_profit:
                attach_algo_ords = []
                
                if params.stop_loss:
                    attach_algo_ords.append({
                        'slTriggerPx': str(params.stop_loss),
                        'slOrdPx': '-1'  # 市价
                    })
                
                if params.take_profit:
                    attach_algo_ords.append({
                        'tpTriggerPx': str(params.take_profit),
                        'tpOrdPx': '-1'  # 市价
                    })
                
                api_params['attachAlgoOrds'] = attach_algo_ords
            
            self.logger.info(f"下单请求: {api_params}")
            
            # 调用API
            response = self.trade_api.set_order(**api_params)
            
            # 处理响应
            if response.get('code') == '0':
                data = response.get('data', [])
                if data:
                    order_data = data[0]
                    result = OrderResult(
                        success=True,
                        order_id=order_data.get('ordId'),
                        client_order_id=order_data.get('clOrdId'),
                        data=order_data
                    )
                    self.logger.info(f"下单成功: {result.order_id}")
                    return result
                else:
                    return OrderResult(
                        success=False,
                        error_message="API返回数据为空"
                    )
            else:
                error_msg = response.get('msg', '未知错误')
                self.logger.error(f"下单失败: {error_msg}")
                return OrderResult(
                    success=False,
                    error_code=response.get('code'),
                    error_message=error_msg
                )
                
        except Exception as e:
            self.logger.error(f"下单异常: {e}")
            return OrderResult(
                success=False,
                error_message=str(e)
            )
    
    def cancel_order(self, inst_id: str, order_id: str = None, 
                    client_order_id: str = None) -> CancelResult:
        """
        撤单
        
        Args:
            inst_id: 产品ID
            order_id: 订单ID
            client_order_id: 客户端订单ID
            
        Returns:
            撤单结果
        """
        if not order_id and not client_order_id:
            return CancelResult(
                success=False,
                error_message="必须提供订单ID或客户端订单ID"
            )
        
        try:
            api_params = {'instId': inst_id}
            
            if order_id:
                api_params['ordId'] = order_id
            if client_order_id:
                api_params['clOrdId'] = client_order_id
            
            self.logger.info(f"撤单请求: {api_params}")
            
            # 调用API
            response = self.trade_api.set_cancel_order(**api_params)
            
            # 处理响应
            if response.get('code') == '0':
                data = response.get('data', [])
                if data:
                    cancel_data = data[0]
                    result = CancelResult(
                        success=True,
                        order_id=cancel_data.get('ordId')
                    )
                    self.logger.info(f"撤单成功: {result.order_id}")
                    return result
                else:
                    return CancelResult(
                        success=False,
                        error_message="API返回数据为空"
                    )
            else:
                error_msg = response.get('msg', '未知错误')
                self.logger.error(f"撤单失败: {error_msg}")
                return CancelResult(
                    success=False,
                    error_code=response.get('code'),
                    error_message=error_msg
                )
                
        except Exception as e:
            self.logger.error(f"撤单异常: {e}")
            return CancelResult(
                success=False,
                error_message=str(e)
            )
    
    def get_positions(self, inst_id: str = None) -> List[PositionInfo]:
        """
        获取持仓信息
        
        Args:
            inst_id: 产品ID，为空则获取所有持仓
            
        Returns:
            持仓信息列表
        """
        try:
            params = {}
            if inst_id:
                params['instId'] = inst_id
            
            response = self.account_api.get_positions(**params)
            
            if response.get('code') == '0':
                positions_data = response.get('data', [])
                positions = []
                
                for pos_data in positions_data:
                    # 只返回有持仓的记录
                    if float(pos_data.get('pos', 0)) != 0:
                        position = PositionInfo(
                            inst_id=pos_data.get('instId'),
                            side=pos_data.get('posSide'),
                            size=float(pos_data.get('pos', 0)),
                            avg_price=float(pos_data.get('avgPx', 0)),
                            unrealized_pnl=float(pos_data.get('upl', 0)),
                            margin=float(pos_data.get('imr', 0)),
                            leverage=int(pos_data.get('lever', 1)),
                            mark_price=float(pos_data.get('markPx', 0))
                        )
                        positions.append(position)
                
                return positions
            else:
                self.logger.error(f"获取持仓失败: {response.get('msg')}")
                return []
                
        except Exception as e:
            self.logger.error(f"获取持仓异常: {e}")
            return []
    
    def close_position(self, inst_id: str, side: str = None, 
                      size: float = None) -> OrderResult:
        """
        平仓
        
        Args:
            inst_id: 产品ID
            side: 持仓方向 (long/short)，为空则平所有方向
            size: 平仓数量，为空则全部平仓
            
        Returns:
            平仓结果
        """
        try:
            api_params = {
                'instId': inst_id,
                'mgnMode': 'isolated'  # 默认逐仓模式
            }
            
            if side:
                api_params['posSide'] = side
            if size:
                api_params['sz'] = str(size)
            
            self.logger.info(f"平仓请求: {api_params}")
            
            # 调用平仓API
            response = self.trade_api.close_positions(**api_params)
            
            # 处理响应
            if response.get('code') == '0':
                data = response.get('data', [])
                if data:
                    close_data = data[0]
                    result = OrderResult(
                        success=True,
                        order_id=close_data.get('ordId'),
                        client_order_id=close_data.get('clOrdId'),
                        data=close_data
                    )
                    self.logger.info(f"平仓成功: {result.order_id}")
                    return result
                else:
                    return OrderResult(
                        success=False,
                        error_message="API返回数据为空"
                    )
            else:
                error_msg = response.get('msg', '未知错误')
                self.logger.error(f"平仓失败: {error_msg}")
                return OrderResult(
                    success=False,
                    error_code=response.get('code'),
                    error_message=error_msg
                )
                
        except Exception as e:
            self.logger.error(f"平仓异常: {e}")
            return OrderResult(
                success=False,
                error_message=str(e)
            )

    def get_pending_orders(self, inst_id: str = None) -> List[Dict]:
        """
        获取未完成订单

        Args:
            inst_id: 产品ID，为空则获取所有订单

        Returns:
            订单信息列表
        """
        try:
            params = {}
            if inst_id:
                params['instId'] = inst_id

            response = self.trade_api.get_orders_pending(**params)

            if response.get('code') == '0':
                return response.get('data', [])
            else:
                self.logger.error(f"获取订单失败: {response.get('msg')}")
                return []

        except Exception as e:
            self.logger.error(f"获取订单异常: {e}")
            return []

    def get_order_details(self, inst_id: str, order_id: str = None,
                         client_order_id: str = None) -> Optional[Dict]:
        """
        获取订单详情

        Args:
            inst_id: 产品ID
            order_id: 订单ID
            client_order_id: 客户端订单ID

        Returns:
            订单详情
        """
        try:
            params = {'instId': inst_id}

            if order_id:
                params['ordId'] = order_id
            if client_order_id:
                params['clOrdId'] = client_order_id

            response = self.trade_api.get_order(**params)

            if response.get('code') == '0':
                data = response.get('data', [])
                return data[0] if data else None
            else:
                self.logger.error(f"获取订单详情失败: {response.get('msg')}")
                return None

        except Exception as e:
            self.logger.error(f"获取订单详情异常: {e}")
            return None

    def batch_cancel_orders(self, orders: List[Dict]) -> List[CancelResult]:
        """
        批量撤单

        Args:
            orders: 订单列表，每个订单包含instId和ordId或clOrdId

        Returns:
            撤单结果列表
        """
        try:
            # 构建批量撤单参数
            cancel_params = []
            for order in orders:
                params = {'instId': order['instId']}
                if 'ordId' in order:
                    params['ordId'] = order['ordId']
                if 'clOrdId' in order:
                    params['clOrdId'] = order['clOrdId']
                cancel_params.append(params)

            self.logger.info(f"批量撤单请求: {len(cancel_params)} 个订单")

            # 调用批量撤单API
            response = self.trade_api.set_cancel_batch_orders(cancel_params)

            results = []
            if response.get('code') == '0':
                data = response.get('data', [])
                for item in data:
                    result = CancelResult(
                        success=item.get('sCode') == '0',
                        order_id=item.get('ordId'),
                        error_code=item.get('sCode'),
                        error_message=item.get('sMsg')
                    )
                    results.append(result)
            else:
                # 如果整个请求失败，为所有订单返回失败结果
                error_msg = response.get('msg', '未知错误')
                for order in orders:
                    results.append(CancelResult(
                        success=False,
                        error_message=error_msg
                    ))

            return results

        except Exception as e:
            self.logger.error(f"批量撤单异常: {e}")
            # 返回失败结果
            return [CancelResult(success=False, error_message=str(e))
                   for _ in orders]

    def get_account_balance(self) -> Dict[str, float]:
        """
        获取账户余额

        Returns:
            余额信息字典 {币种: 余额}
        """
        try:
            response = self.account_api.get_balance()

            if response.get('code') == '0':
                balances = {}
                data = response.get('data', [])

                if data:
                    details = data[0].get('details', [])
                    for detail in details:
                        ccy = detail.get('ccy')
                        balance = float(detail.get('bal', 0))
                        if balance > 0:
                            balances[ccy] = balance

                return balances
            else:
                self.logger.error(f"获取余额失败: {response.get('msg')}")
                return {}

        except Exception as e:
            self.logger.error(f"获取余额异常: {e}")
            return {}
