#!/bin/bash
# Kronos Web Dashboard 启动脚本

echo "🚀 启动Kronos Web Dashboard"
echo "================================"

# 激活虚拟环境
source .venv/bin/activate

# 检查数据库是否存在
if [ ! -f "./data/predictions.db" ]; then
    echo "⚠️ 数据库文件不存在，请先运行预测系统生成数据："
    echo "   ./start_continuous.sh production"
    echo ""
    echo "或者运行快速测试生成一些数据："
    echo "   ./start_continuous.sh quick"
    exit 1
fi

# 检查参数
if [ "$1" = "dev" ]; then
    echo "🔧 开发模式（调试开启）..."
    python web_dashboard.py --host 127.0.0.1 --port 5000 --debug
elif [ "$1" = "public" ]; then
    echo "🌐 公网模式（所有IP可访问）..."
    python web_dashboard.py --host 0.0.0.0 --port 8080
elif [ "$1" = "local" ]; then
    echo "🏠 本地模式（仅本机访问）..."
    python web_dashboard.py --host 127.0.0.1 --port 8080
else
    echo "🔧 可用参数："
    echo "  dev     - 开发模式（127.0.0.1:5000，调试开启）"
    echo "  local   - 本地模式（127.0.0.1:8080）"
    echo "  public  - 公网模式（0.0.0.0:8080，所有IP可访问）"
    echo ""
    echo "启动默认模式（本地访问）..."
    python web_dashboard.py --host 127.0.0.1 --port 8080
fi
