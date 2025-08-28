# OKX-Kronos 虚拟交易测试指南

## 🎯 概述

虚拟交易测试系统允许你使用虚拟资金长期测试策略效果，完全不涉及真实资金，但使用真实的市场数据和价格。

## 🚀 快速开始

### 1. 启动虚拟交易测试

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动虚拟交易测试
python run_virtual_trading_test.py
```

### 2. 测试配置

默认配置：
- **初始资金**: $100,000 USDT (虚拟)
- **测试时长**: 24小时
- **交易品种**: BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP
- **最大持仓**: 3个
- **单次仓位**: 15%资金
- **止损**: 3%
- **止盈**: 6%

### 3. 实时监控

测试运行时会显示：
- 当前权益
- 收益率
- 持仓数量
- 交易统计

## 📊 策略说明

### 当前使用的示例策略

结合多个技术指标的综合策略：

1. **RSI指标** (权重30%)
   - RSI < 30: 超卖，买入信号
   - RSI > 70: 超买，卖出信号

2. **移动平均线交叉** (权重30%)
   - 短期MA(10)上穿长期MA(30): 金叉买入
   - 短期MA(10)下穿长期MA(30): 死叉卖出

3. **布林带** (权重20%)
   - 价格触及下轨: 买入信号
   - 价格触及上轨: 卖出信号

4. **成交量确认** (权重20%)
   - 成交量放大确认信号强度

### 信号生成逻辑

- 综合评分 > 0.3 才会产生交易信号
- 买入和卖出信号互斥
- 考虑信号强度和置信度

## 🔧 自定义策略

### 1. 创建新策略文件

```python
# src/strategies/my_strategy.py
from typing import Optional, Dict
from ..common.signals import TradingSignal, SignalType

def my_strategy_function(instrument: str, market_data: Dict) -> Optional[TradingSignal]:
    """
    自定义策略函数
    
    Args:
        instrument: 交易品种 (如 'BTC-USDT-SWAP')
        market_data: 市场数据
            - current_price: 当前价格
            - klines: 历史K线数据 (pandas DataFrame)
            - timestamp: 数据时间戳
    
    Returns:
        TradingSignal 或 None
    """
    current_price = market_data['current_price']
    df = market_data['klines']
    
    # 你的策略逻辑
    # ...
    
    # 返回信号
    return TradingSignal(
        signal_type=SignalType.BUY,  # BUY/SELL/HOLD
        strength=0.8,                # 信号强度 0-1
        confidence=0.75,             # 置信度 0-1
        entry_price=current_price,   # 入场价格
        reason="我的策略信号"         # 信号原因
    )
```

### 2. 修改启动脚本

在 `run_virtual_trading_test.py` 中：

```python
# 替换这行
from src.strategies.example_strategy import strategy_function

# 为
from src.strategies.my_strategy import my_strategy_function as strategy_function
```

## 📈 测试结果分析

### 1. 实时状态

测试过程中会显示：
```
⏰ 14:30:15 | 权益: $102,350.00 | 收益: +2.35% | 持仓: 2
```

### 2. 最终报告

测试结束后会显示详细结果：
```
📋 虚拟交易测试结果
====================================
测试时间: 2024-01-15 10:00:00 - 2024-01-16 10:00:00
初始资金: $100,000.00
最终资金: $103,250.00
总收益: +$3,250.00 (+3.25%)
最大回撤: 1.50%
夏普比率: 1.25
总交易次数: 15
胜率: 66.7% (10/15)
平均盈利: $450.00
平均亏损: $-180.00
盈亏比: 2.50
总手续费: $125.00
```

### 3. 保存的文件

- `virtual_trading_test_account_YYYYMMDD_HHMMSS.json`: 详细账户状态
- `virtual_trading_test_result_YYYYMMDD_HHMMSS.json`: 回测结果摘要

## ⚙️ 高级配置

### 1. 修改测试参数

在 `run_virtual_trading_test.py` 的 `create_test_config()` 函数中：

```python
config = BacktestConfig(
    instruments=['BTC-USDT-SWAP', 'ETH-USDT-SWAP'],  # 交易品种
    initial_balance=50000.0,      # 初始资金
    test_duration_hours=48,       # 测试48小时
    price_update_interval=15,     # 15秒更新价格
    strategy_check_interval=30,   # 30秒检查策略
    max_positions=5,              # 最多5个持仓
    position_size_pct=0.10,       # 每次10%资金
    stop_loss_pct=0.02,           # 2%止损
    take_profit_pct=0.05          # 5%止盈
)
```

### 2. 添加更多交易品种

支持的品种格式：`{BASE}-{QUOTE}-SWAP`

常见品种：
- `BTC-USDT-SWAP`
- `ETH-USDT-SWAP`
- `SOL-USDT-SWAP`
- `ADA-USDT-SWAP`
- `DOT-USDT-SWAP`

## 🛡️ 风险说明

### ✅ 安全保障

1. **完全虚拟**: 不使用任何真实资金
2. **真实数据**: 使用真实市场价格和数据
3. **真实环境**: 模拟真实交易环境（滑点、手续费等）
4. **无风险测试**: 可以安全测试任何策略

### ⚠️ 注意事项

1. **网络连接**: 需要稳定的网络连接获取实时价格
2. **API限制**: 受OKX API调用频率限制
3. **数据延迟**: 可能有轻微的数据延迟
4. **模拟环境**: 与真实交易可能有细微差异

## 🔍 故障排除

### 常见问题

1. **无法获取价格数据**
   - 检查网络连接
   - 确认OKX API可访问
   - 检查交易品种名称是否正确

2. **策略不生成信号**
   - 检查策略逻辑
   - 确认数据足够（需要足够的历史K线）
   - 查看日志文件了解详情

3. **测试意外停止**
   - 查看日志文件
   - 检查系统资源
   - 确认没有网络中断

### 日志文件

每次测试都会生成日志文件：`virtual_trading_YYYYMMDD_HHMMSS.log`

包含详细的：
- 价格更新记录
- 策略信号生成
- 交易执行详情
- 错误和异常信息

## 📞 支持

如果遇到问题：

1. 查看日志文件
2. 检查网络和API连接
3. 确认配置参数正确
4. 验证策略逻辑

## 🎯 最佳实践

1. **从小额开始**: 先用较小的虚拟资金测试
2. **短期验证**: 先进行短期测试验证策略
3. **参数调优**: 根据结果调整策略参数
4. **风险控制**: 设置合理的止损和止盈
5. **多品种测试**: 在不同品种上验证策略效果
6. **长期观察**: 进行足够长时间的测试以获得统计意义

---

**祝你测试顺利！** 🚀
