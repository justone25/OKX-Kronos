#!/bin/bash
# OKX持仓和订单快速查询脚本

# 激活虚拟环境
source .venv/bin/activate

echo "🚀 OKX持仓和订单查询工具"
echo "================================"

# 检查参数
case "$1" in
    "positions"|"pos")
        echo "📊 查询持仓信息..."
        python okx_positions_orders.py --positions
        ;;
    "orders"|"ord")
        echo "📋 查询未完成订单..."
        python okx_positions_orders.py --orders
        ;;
    "algo")
        echo "🤖 查询算法订单..."
        python okx_positions_orders.py --algo-orders
        ;;
    "btc")
        echo "🪙 查询BTC相关信息..."
        python okx_positions_orders.py --all --inst-id BTC-USDT-SWAP
        ;;
    "eth")
        echo "💎 查询ETH相关信息..."
        python okx_positions_orders.py --all --inst-id ETH-USDT-SWAP
        ;;
    "swap")
        echo "🔄 查询所有永续合约..."
        python okx_positions_orders.py --all --inst-type SWAP
        ;;
    "spot")
        echo "💰 查询现货交易..."
        python okx_positions_orders.py --all --inst-type SPOT
        ;;
    "json")
        echo "📄 JSON格式输出..."
        python okx_positions_orders.py --all --json
        ;;
    "help"|"-h"|"--help")
        echo "📖 使用说明:"
        echo "  ./check_positions.sh [选项]"
        echo ""
        echo "选项:"
        echo "  positions, pos  - 只查询持仓信息"
        echo "  orders, ord     - 只查询未完成订单"
        echo "  algo           - 只查询算法订单"
        echo "  btc            - 查询BTC-USDT-SWAP相关信息"
        echo "  eth            - 查询ETH-USDT-SWAP相关信息"
        echo "  swap           - 查询所有永续合约"
        echo "  spot           - 查询现货交易"
        echo "  json           - JSON格式输出所有信息"
        echo "  help           - 显示此帮助信息"
        echo ""
        echo "无参数时默认查询所有信息"
        ;;
    "")
        echo "📊 查询所有信息..."
        python okx_positions_orders.py --all
        ;;
    *)
        echo "❌ 未知选项: $1"
        echo "💡 使用 './check_positions.sh help' 查看帮助"
        exit 1
        ;;
esac
