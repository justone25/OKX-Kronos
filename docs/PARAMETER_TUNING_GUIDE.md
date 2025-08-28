# Kronos参数调优指南

## 🎯 当前参数分析

### 现有配置问题诊断
- **数据窗口**: 12小时 → **可能不足以捕捉BTC的日内周期**
- **预测长度**: 3小时 → **合理，但可以测试更短期预测**
- **采样温度**: 1.0 → **可能过于随机，降低确定性**
- **Top-p**: 0.9 → **合理范围**
- **采样次数**: 1 → **单次采样可能不够稳定**
- **更新频率**: 15分钟 → **合理**

## 📊 参数影响分析

### 1. 数据窗口 (lookback_hours)
**当前**: 12小时 (144个5分钟K线)

**问题**:
- BTC有明显的24小时周期性
- 12小时可能错过重要的日内模式
- 无法捕捉隔夜市场变化

**建议优化**:
```bash
# 测试24小时窗口
--lookback 24  # 288个5分钟K线

# 测试48小时窗口 (包含周末效应)
--lookback 48  # 576个5分钟K线
```

**预期效果**: 提高趋势识别准确性，更好的周期性捕捉

### 2. 采样温度 (temperature)
**当前**: 1.0

**问题**:
- 温度1.0产生较高随机性
- 可能导致预测不够稳定
- 对于价格预测，过度随机性不利

**建议优化**:
```python
# 在 prediction_scheduler.py 中修改
self.temperature = 0.7  # 降低随机性，提高确定性
# 或者
self.temperature = 0.8  # 平衡随机性和确定性
```

**预期效果**: 更稳定的预测结果，减少噪音

### 3. 采样次数 (sample_count)
**当前**: 1

**问题**:
- 单次采样容易受随机性影响
- 无法利用模型的不确定性量化
- 预测结果可能不够鲁棒

**建议优化**:
```python
# 多样本采样取平均
self.sample_count = 3  # 3次采样取平均
# 或者
self.sample_count = 5  # 5次采样取平均 (更稳定但更慢)
```

**预期效果**: 更稳定的预测，更好的不确定性量化

### 4. 预测时长 (pred_hours)
**当前**: 3小时

**建议测试**:
```bash
# 短期预测 (可能更准确)
--pred-hours 1  # 1小时预测

# 中期预测
--pred-hours 2  # 2小时预测

# 保持当前
--pred-hours 3  # 3小时预测
```

**原理**: 短期预测通常更准确，长期预测不确定性增加

## 🚀 推荐优化方案

### 方案1: 保守优化 (推荐)
```bash
# 启动命令
python continuous_prediction.py \
  --interval 15 \
  --lookback 24 \
  --pred-hours 2 \
  --device auto

# 调度器参数 (修改 prediction_scheduler.py)
self.temperature = 0.8
self.top_p = 0.9
self.sample_count = 3
```

**优势**: 平衡性能和准确性，适合生产环境

### 方案2: 高精度优化
```bash
# 启动命令
python continuous_prediction.py \
  --interval 15 \
  --lookback 48 \
  --pred-hours 1 \
  --device auto

# 调度器参数
self.temperature = 0.6
self.top_p = 0.85
self.sample_count = 5
```

**优势**: 最高精度，但计算成本较高

### 方案3: 快速响应优化
```bash
# 启动命令
python continuous_prediction.py \
  --interval 10 \
  --lookback 24 \
  --pred-hours 1 \
  --device auto

# 调度器参数
self.temperature = 0.7
self.top_p = 0.9
self.sample_count = 3
```

**优势**: 快速响应市场变化，适合高频交易

## 🧪 参数测试工具

### 自动化参数优化
```bash
# 运行参数优化测试
python parameter_optimization.py
```

这个工具会自动测试多种参数组合并给出推荐。

### 手动A/B测试
```bash
# 测试方案A (当前)
./start_continuous.sh quick

# 等待收集数据后，测试方案B
python continuous_prediction.py --interval 15 --lookback 24 --pred-hours 2
```

## 📈 评估指标

### 1. 预测准确性指标
- **方向准确率**: 预测涨跌方向的正确率
- **价格误差**: 预测价格与实际价格的差异
- **趋势捕捉**: 能否识别重要的价格趋势

### 2. 系统性能指标
- **预测速度**: 单次预测的耗时
- **资源占用**: CPU和内存使用率
- **稳定性**: 预测结果的一致性

### 3. 实用性指标
- **响应速度**: 对市场变化的反应时间
- **可操作性**: 预测结果的可交易性
- **风险控制**: 预测的不确定性量化

## 🔧 实施步骤

### 第1步: 备份当前配置
```bash
# 确保v1.0版本安全
cd ../OKX-Kronos-v1.0
./start_continuous.sh status  # 确认当前运行状态
```

### 第2步: 在主分支测试新参数
```bash
cd ../OKX-Kronos

# 修改 src/scheduler/prediction_scheduler.py
# 更新推荐参数
```

### 第3步: 运行参数优化测试
```bash
python parameter_optimization.py
```

### 第4步: 应用最佳配置
```bash
# 根据测试结果应用最佳配置
./start_continuous.sh production
```

### 第5步: 监控和评估
```bash
# 运行24小时后评估效果
./start_continuous.sh status
./start_continuous.sh trends
```

## 💡 高级优化技巧

### 1. 动态参数调整
根据市场波动性动态调整温度参数：
- 高波动期: 降低温度 (0.6-0.7)
- 低波动期: 提高温度 (0.8-0.9)

### 2. 时间段优化
不同时间段使用不同参数：
- 亚洲交易时段: 较长回看窗口
- 欧美交易时段: 较短预测时长
- 周末: 增加采样次数

### 3. 市场状态适应
根据市场趋势调整：
- 趋势市场: 增加预测时长
- 震荡市场: 减少预测时长，增加采样次数

## 🎯 预期改进效果

通过参数优化，预期可以实现：
- **预测准确性提升**: 10-20%
- **方向判断准确率**: 提升至70-80%
- **预测稳定性**: 显著改善
- **市场适应性**: 更好的周期性捕捉

开始优化吧！🚀
