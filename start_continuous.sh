#!/bin/bash
# Kronos持续预测系统启动脚本

echo "🚀 启动Kronos持续预测系统"
echo "================================"

# 激活虚拟环境
source .venv/bin/activate

# 检查参数
if [ "$1" = "status" ]; then
    echo "📊 查看系统状态..."
    python continuous_prediction.py --mode status
elif [ "$1" = "trends" ]; then
    echo "📈 显示预测趋势..."
    python continuous_prediction.py --mode trends --hours ${2:-24}
elif [ "$1" = "export" ]; then
    if [ -z "$2" ]; then
        echo "❌ 导出模式需要指定输出文件路径"
        echo "用法: ./start_continuous.sh export output.csv [hours]"
        exit 1
    fi
    echo "💾 导出预测数据..."
    python continuous_prediction.py --mode export --output "$2" --hours ${3:-24}
elif [ "$1" = "quick" ]; then
    echo "⚡ 快速测试模式（每2分钟预测一次，使用GPU加速）..."
    python continuous_prediction.py --interval 2 --lookback 6 --pred-hours 1 --device auto
elif [ "$1" = "production" ]; then
    echo "🏭 生产模式（每30分钟预测一次，使用GPU加速）..."
    python continuous_prediction.py --interval 30 --lookback 24 --pred-hours 6 --device auto
elif [ "$1" = "gpu" ]; then
    echo "🚀 GPU加速模式（15分钟间隔，MPS加速）..."
    python continuous_prediction.py --interval 15 --lookback 12 --pred-hours 3 --device mps
elif [ "$1" = "deterministic" ]; then
    echo "🔒 确定性模式（结果可重现）..."
    python continuous_prediction.py --interval 15 --lookback 12 --pred-hours 3 --device auto
else
    echo "🔧 自定义配置模式..."
    echo "可用参数："
    echo "  status        - 查看系统状态"
    echo "  trends        - 显示预测趋势"
    echo "  export        - 导出数据"
    echo "  quick         - 快速测试（2分钟间隔，GPU加速）"
    echo "  production    - 生产模式（30分钟间隔，GPU加速）"
    echo "  gpu           - GPU加速模式（15分钟间隔，MPS加速）"
    echo "  deterministic - 确定性模式（结果可重现）"
    echo ""
    echo "启动默认配置（15分钟间隔，自动选择最优设备）..."
    python continuous_prediction.py --interval 15 --lookback 12 --pred-hours 3 --device auto
fi
