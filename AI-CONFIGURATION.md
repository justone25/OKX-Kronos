# 🤖 Kronos AI配置指南

## 📋 AI服务概述

Kronos多币种预测系统使用**智谱AI (ZhipuAI)**作为核心的AI预测引擎，提供专业的加密货币价格分析和预测服务。

## 🔑 智谱AI API密钥获取

### 1. 注册智谱AI账户
访问 [智谱AI开放平台](https://open.bigmodel.cn/) 注册账户

### 2. 创建API密钥
1. 登录后进入控制台
2. 点击"API管理" → "创建新的API Key"
3. 复制生成的API密钥

### 3. 配置API密钥
在`.env`文件中设置：
```bash
ZHIPU_API_KEY=your_actual_zhipu_api_key_here
```

## 🧠 AI功能说明

### 核心AI组件

1. **智谱AI预测器** (`ZhipuAIPredictor`)
   - 使用GLM-4模型进行价格预测
   - 分析市场数据和历史价格
   - 提供预测方向、置信度和目标价格

2. **Kronos预测器** (`KronosPredictor`)
   - 集成多种预测算法
   - 结合技术指标和AI分析
   - 生成综合预测结果

3. **交易决策AI**
   - 基于预测结果做交易决策
   - 评估风险和收益
   - 提供买入/卖出/持有建议

### AI预测流程

```
市场数据 → 智谱AI分析 → 预测结果 → 交易决策 → 执行建议
    ↓           ↓           ↓           ↓           ↓
  价格历史    GLM-4模型    方向+置信度   风险评估    具体操作
  技术指标    自然语言     目标价格     收益预期    仓位管理
  市场情绪    推理分析     时间范围     止损设置    执行时机
```

## ⚙️ AI配置参数

### 模型参数
```bash
# 智谱AI模型配置
MODEL_TEMPERATURE=0.8    # 采样温度 (0.1-2.0)
MODEL_TOP_P=0.9         # Top-p采样 (0.1-1.0)
MODEL_SAMPLE_COUNT=1    # 采样次数 (1-5)

# 预测参数
LOOKBACK_HOURS=24       # 历史数据回看时间
PREDICTION_HOURS=2      # 预测时间范围
```

### 参数说明

| 参数 | 范围 | 说明 | 推荐值 |
|------|------|------|--------|
| `TEMPERATURE` | 0.1-2.0 | 控制输出随机性，越低越保守 | 0.8 |
| `TOP_P` | 0.1-1.0 | 控制词汇选择范围 | 0.9 |
| `SAMPLE_COUNT` | 1-5 | 生成预测的次数 | 1 |
| `LOOKBACK_HOURS` | 6-72 | 分析历史数据的时间长度 | 24 |
| `PREDICTION_HOURS` | 1-24 | 预测未来的时间范围 | 2 |

## 🔍 AI预测示例

### 输入数据
```json
{
  "instrument": "BTC-USDT-SWAP",
  "current_price": 65000.00,
  "price_history": [64800, 64900, 65100, 65000],
  "volume": 1250000,
  "technical_indicators": {
    "rsi": 58.5,
    "macd": 0.15,
    "bollinger_position": 0.6
  }
}
```

### AI分析输出
```json
{
  "direction": "up",
  "confidence": 0.75,
  "target_price": 66200.00,
  "time_horizon": 2,
  "reasoning": "基于技术指标分析，RSI处于中性偏多区域，MACD显示上涨动能，布林带位置表明价格有上行空间。结合当前市场情绪和历史价格模式，预计短期内价格将上涨至66200附近。",
  "risk_level": "medium",
  "stop_loss": 64200.00,
  "take_profit": 66500.00
}
```

## 🚨 重要注意事项

### 1. API密钥安全
- ❌ **不要**将API密钥提交到代码仓库
- ✅ **使用**环境变量存储密钥
- ✅ **定期**更换API密钥
- ✅ **限制**API密钥的访问权限

### 2. API使用限制
- **调用频率**：智谱AI有API调用频率限制
- **成本控制**：每次调用都会产生费用
- **缓存机制**：系统内置5分钟预测缓存
- **错误处理**：API失败时使用备用预测

### 3. 预测准确性
- AI预测仅供参考，不构成投资建议
- 市场波动性高，预测存在不确定性
- 建议结合多种分析方法
- 严格执行风险管理策略

## 🔧 故障排除

### 常见问题

1. **API密钥无效**
   ```
   错误：智谱AI API密钥未设置或无效
   解决：检查.env文件中的ZHIPU_API_KEY配置
   ```

2. **API调用失败**
   ```
   错误：智谱AI API调用超时或失败
   解决：检查网络连接，确认API密钥有效，查看调用频率限制
   ```

3. **预测结果异常**
   ```
   错误：AI返回的预测结果格式不正确
   解决：检查输入数据格式，调整模型参数，查看API响应日志
   ```

### 调试命令

```bash
# 测试AI连接
docker-compose exec kronos-app python -c "
import os
from src.ai.zhipu_predictor import ZhipuAIPredictor
predictor = ZhipuAIPredictor()
print('AI连接测试成功')
"

# 查看AI预测日志
docker-compose logs -f kronos-app | grep -i "zhipu\|ai\|predict"

# 检查环境变量
docker-compose exec kronos-app env | grep ZHIPU
```

## 📊 性能优化

### 1. 缓存策略
- 相同输入5分钟内使用缓存结果
- 减少不必要的API调用
- 降低成本和延迟

### 2. 批量处理
- 多个交易对可以批量分析
- 合理安排API调用时间
- 避免并发调用过多

### 3. 降级策略
- AI服务不可用时使用技术指标
- 保证系统持续运行
- 记录降级事件用于分析

## 💰 成本估算

### 智谱AI定价（参考）
- GLM-4模型：约 ¥0.1/1K tokens
- 每次预测约消耗 500-1000 tokens
- 24个交易对，30分钟间隔：
  - 每小时：48次调用
  - 每天：1152次调用
  - 月成本：约 ¥50-100

### 成本优化建议
1. 合理设置预测间隔
2. 使用缓存减少重复调用
3. 监控API使用量
4. 根据市场活跃度调整频率

---

## 🎯 配置检查清单

部署前请确认：

- [ ] 已获取智谱AI API密钥
- [ ] 在`.env`文件中正确配置`ZHIPU_API_KEY`
- [ ] API密钥有足够的调用额度
- [ ] 网络可以访问智谱AI服务
- [ ] 已测试AI连接和预测功能
- [ ] 了解API调用成本和限制
- [ ] 配置了适当的错误处理和降级策略

✅ **配置完成后，Kronos系统将具备强大的AI预测能力，为多币种交易提供智能决策支持！**
