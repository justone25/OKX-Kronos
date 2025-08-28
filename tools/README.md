# 工具脚本目录

本目录包含各种工具脚本和启动程序。

## 🚀 统一启动器

- `kronos_launcher.py` - 统一启动器，整合所有功能

## 📊 核心工具

- `run_daytime_strategy.py` - 启动白天震荡策略
- `benchmark_devices.py` - 设备性能基准测试
- `check_validation_timing.py` - 检查验证时机
- `okx_positions_orders.py` - OKX 持仓和订单查询
- `parameter_optimization.py` - 参数优化工具
- `quick_parameter_test.py` - 快速参数测试

## 使用方法

### 统一启动器（推荐）

```bash
# 🚀 一键启动（默认）- 预测服务 + Web面板
python tools/kronos_launcher.py
# 或者
python tools/kronos_launcher.py start

# 自定义参数启动
python tools/kronos_launcher.py start --port 8080 --instruments 12

# 查看所有可用命令
python tools/kronos_launcher.py help

# 单独启动各个服务
python tools/kronos_launcher.py strategy                    # 白天震荡策略
python tools/kronos_launcher.py predict --mode continuous   # 仅预测服务
python tools/kronos_launcher.py dashboard --port 8080       # 仅Web面板
python tools/kronos_launcher.py positions                   # 查询持仓
python tools/kronos_launcher.py benchmark                   # 基准测试
python tools/kronos_launcher.py status                      # 查看状态
```

**🎯 默认参数设置：**

- 交易对数量：24 个
- 预测模式：batch（批量预测）
- 预测间隔：10 分钟
- 自动验证：开启
- Web 端口：5000

### 直接调用（传统方式）

```bash
# 启动策略
python tools/run_daytime_strategy.py

# 启动Kronos预测服务
python examples/kronos_multi_prediction.py --mode continuous --instruments 24
```
