#!/usr/bin/env python3
"""
OKX持仓和订单查询工具
根据OKX API文档获取当前所有的合约持仓和订单信息
"""
import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Any
import json

# 添加src目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from okx.api import Account, Trade, AlgoTrade
from src.utils.config import OKXConfig

class OKXPositionsOrdersClient:
    """OKX持仓和订单查询客户端"""

    def __init__(self, config: OKXConfig):
        """初始化客户端"""
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 初始化API客户端
        self.account_api = Account(
            key=config.api_key,
            secret=config.secret_key,
            passphrase=config.passphrase,
            flag='0'  # 0: 实盘, 1: 模拟盘
        )

        self.trade_api = Trade(
            key=config.api_key,
            secret=config.secret_key,
            passphrase=config.passphrase,
            flag='0'  # 0: 实盘, 1: 模拟盘
        )

        self.algo_trade_api = AlgoTrade(
            key=config.api_key,
            secret=config.secret_key,
            passphrase=config.passphrase,
            flag='0'  # 0: 实盘, 1: 模拟盘
        )
    
    def get_positions(self, inst_id: str = None) -> List[Dict[str, Any]]:
        """
        获取持仓信息
        
        Args:
            inst_id: 产品ID，如BTC-USDT-SWAP，为空则获取所有持仓
            
        Returns:
            持仓信息列表
        """
        try:
            params = {}
            if inst_id:
                params['instId'] = inst_id
                
            response = self.account_api.get_positions(**params)
            
            if response['code'] == '0':
                return response['data']
            else:
                self.logger.error(f"获取持仓失败: {response['msg']}")
                return []
                
        except Exception as e:
            self.logger.error(f"获取持仓异常: {e}")
            return []
    
    def get_pending_orders(self, inst_type: str = None, inst_id: str = None) -> List[Dict[str, Any]]:
        """
        获取未完成订单
        
        Args:
            inst_type: 产品类型 SPOT, MARGIN, SWAP, FUTURES, OPTION
            inst_id: 产品ID
            
        Returns:
            订单信息列表
        """
        try:
            params = {}
            if inst_type:
                params['instType'] = inst_type
            if inst_id:
                params['instId'] = inst_id
                
            response = self.trade_api.get_orders_pending(**params)
            
            if response['code'] == '0':
                return response['data']
            else:
                self.logger.error(f"获取订单失败: {response['msg']}")
                return []
                
        except Exception as e:
            self.logger.error(f"获取订单异常: {e}")
            return []
    
    def get_algo_orders(self, inst_type: str = None, inst_id: str = None) -> List[Dict[str, Any]]:
        """
        获取算法订单

        Args:
            inst_type: 产品类型
            inst_id: 产品ID

        Returns:
            算法订单信息列表
        """
        try:
            params = {
                'ordType': 'conditional'  # 默认查询条件单
            }
            if inst_type:
                params['instType'] = inst_type
            if inst_id:
                params['instId'] = inst_id

            response = self.algo_trade_api.get_orders_algo_pending(**params)
            
            if response['code'] == '0':
                return response['data']
            else:
                self.logger.error(f"获取算法订单失败: {response['msg']}")
                return []
                
        except Exception as e:
            self.logger.error(f"获取算法订单异常: {e}")
            return []

def safe_float(value, default=0.0):
    """安全转换为浮点数"""
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

def format_position_info(position: Dict[str, Any]) -> str:
    """格式化持仓信息"""
    inst_id = position.get('instId', 'N/A')
    pos_side = position.get('posSide', 'N/A')
    pos = safe_float(position.get('pos', 0))
    avg_px = safe_float(position.get('avgPx', 0))
    upl = safe_float(position.get('upl', 0))
    upl_ratio = safe_float(position.get('uplRatio', 0)) * 100

    # 使用imr（初始保证金）而不是margin字段
    margin = safe_float(position.get('imr', 0))

    # 获取当前价格（优先使用标记价格，其次最新价格）
    current_px = safe_float(position.get('markPx', 0))
    if current_px == 0:
        current_px = safe_float(position.get('last', 0))

    lever = position.get('lever', 'N/A')

    # 持仓方向显示
    side_display = {
        'long': '多头',
        'short': '空头',
        'net': '净持仓'
    }.get(pos_side, pos_side)

    return f"""
  📊 {inst_id} ({side_display})
     持仓数量: {pos:,.4f}
     开仓均价: ${avg_px:,.4f}
     当前价格: ${current_px:,.4f}
     未实现盈亏: ${upl:,.2f} ({upl_ratio:+.2f}%)
     保证金: ${margin:,.2f}
     杠杆倍数: {lever}x"""

def format_order_info(order: Dict[str, Any]) -> str:
    """格式化订单信息"""
    inst_id = order.get('instId', 'N/A')
    ord_type = order.get('ordType', 'N/A')
    side = order.get('side', 'N/A')
    sz = safe_float(order.get('sz', 0))
    px = safe_float(order.get('px', 0))
    state = order.get('state', 'N/A')
    ord_id = order.get('ordId', 'N/A')
    
    # 订单类型显示
    type_display = {
        'market': '市价单',
        'limit': '限价单',
        'post_only': '只做Maker',
        'fok': '全部成交或立即取消',
        'ioc': '立即成交并取消剩余'
    }.get(ord_type, ord_type)
    
    # 买卖方向显示
    side_display = {
        'buy': '买入',
        'sell': '卖出'
    }.get(side, side)
    
    # 订单状态显示
    state_display = {
        'live': '等待成交',
        'partially_filled': '部分成交',
        'filled': '完全成交',
        'canceled': '已撤销'
    }.get(state, state)
    
    price_info = f"${px:,.4f}" if px > 0 else "市价"
    
    return f"""
  📋 订单ID: {ord_id}
     交易对: {inst_id}
     类型: {type_display} | {side_display}
     数量: {sz:,.4f}
     价格: {price_info}
     状态: {state_display}"""

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='OKX持仓和订单查询工具')
    parser.add_argument('--positions', action='store_true', help='显示持仓信息')
    parser.add_argument('--orders', action='store_true', help='显示未完成订单')
    parser.add_argument('--algo-orders', action='store_true', help='显示算法订单')
    parser.add_argument('--all', action='store_true', help='显示所有信息')
    parser.add_argument('--inst-id', type=str, help='指定产品ID，如BTC-USDT-SWAP')
    parser.add_argument('--inst-type', type=str, help='指定产品类型：SPOT, MARGIN, SWAP, FUTURES, OPTION')
    parser.add_argument('--json', action='store_true', help='以JSON格式输出')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 如果没有指定任何选项，默认显示所有信息
    if not any([args.positions, args.orders, args.algo_orders]):
        args.all = True
    
    try:
        # 加载配置
        config = OKXConfig()
        
        # 检查API配置
        if not all([config.api_key, config.secret_key, config.passphrase]):
            print("❌ 错误: 请在 config/.env 文件中设置 OKX API 配置")
            print("   需要设置: OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE")
            return 1
        
        # 创建客户端
        client = OKXPositionsOrdersClient(config)
        
        print("🚀 OKX 持仓和订单查询工具")
        print("=" * 60)
        print(f"⏰ 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if args.inst_id:
            print(f"🎯 指定产品: {args.inst_id}")
        if args.inst_type:
            print(f"📊 指定类型: {args.inst_type}")
        
        print("=" * 60)
        
        results = {}
        
        # 获取持仓信息
        if args.positions or args.all:
            print("\n💰 持仓信息:")
            positions = client.get_positions(args.inst_id)
            results['positions'] = positions
            
            if positions:
                for pos in positions:
                    if safe_float(pos.get('pos', 0)) != 0:  # 只显示有持仓的
                        if args.json:
                            print(json.dumps(pos, indent=2, ensure_ascii=False))
                        else:
                            # 调试：先打印原始数据
                            if args.verbose:
                                print(f"原始持仓数据: {json.dumps(pos, indent=2, ensure_ascii=False)}")
                            print(format_position_info(pos))
            else:
                print("  📭 暂无持仓")
        
        # 获取未完成订单
        if args.orders or args.all:
            print("\n📋 未完成订单:")
            orders = client.get_pending_orders(args.inst_type, args.inst_id)
            results['orders'] = orders
            
            if orders:
                for order in orders:
                    if args.json:
                        print(json.dumps(order, indent=2, ensure_ascii=False))
                    else:
                        print(format_order_info(order))
            else:
                print("  📭 暂无未完成订单")
        
        # 获取算法订单
        if args.algo_orders or args.all:
            print("\n🤖 算法订单:")
            algo_orders = client.get_algo_orders(args.inst_type, args.inst_id)
            results['algo_orders'] = algo_orders
            
            if algo_orders:
                for order in algo_orders:
                    if args.json:
                        print(json.dumps(order, indent=2, ensure_ascii=False))
                    else:
                        print(format_order_info(order))
            else:
                print("  📭 暂无算法订单")
        
        # JSON输出模式
        if args.json and not any([args.positions, args.orders, args.algo_orders]):
            print(json.dumps(results, indent=2, ensure_ascii=False))
        
        print("\n" + "=" * 60)
        print("✅ 查询完成")
        
        return 0
        
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
