# OKX-Kronos 智能交易系统

基于多信号源融合的比特币合约交易策略系统，集成技术指标、AI 预测和深度学习模型。

## 🏗️ 项目结构

```
OKX-Kronos/
├── src/                    # 核心代码
│   ├── ai/                 # AI预测模块
│   ├── common/             # 公共组件
│   ├── data/               # 数据获取
│   ├── strategies/         # 交易策略
│   ├── trading/            # 交易执行
│   ├── utils/              # 工具函数
│   └── validation/         # 预测验证
├── config/                 # 配置文件
├── tools/                  # 工具脚本
├── examples/               # 示例程序
├── docs/                   # 文档
├── data/                   # 数据文件
├── models/                 # 模型文件
├── static/                 # 静态资源
└── templates/              # 模板文件
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

编辑 `config/` 目录下的配置文件，填入你的 OKX API 密钥。

### 3. 一键启动 Kronos 服务

```bash
# 启动多币种预测服务 + Web监控面板
python tools/kronos_launcher.py
```

### 4. 启动交易策略（可选）

```bash
python tools/kronos_launcher.py strategy
```

## 📊 核心功能

- **多币种 Kronos 预测**: 24 个交易对并发预测，自动验证准确性
- **智能信号融合**: 技术指标 + 智谱 AI + Kronos 深度学习预测
- **实时 Web 监控**: 预测趋势、验证结果、交易状态一目了然
- **自动验证系统**: 持续验证预测准确性，提供详细统计
- **一键启动**: 预测服务 + Web 面板同时启动，开箱即用

## 🛡️ 风险提示

本系统仅供学习和研究使用，实盘交易存在风险，请谨慎使用。

## 📚 文档

详细文档请查看 `docs/` 目录。

## 🧪 测试

项目使用内置的验证系统进行预测准确性测试。

## 📄 许可证

MIT License
