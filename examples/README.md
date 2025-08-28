# 示例程序目录

本目录包含各种示例程序和主要应用。

## 主要程序
- `main.py` - 主程序入口
- `continuous_prediction.py` - 连续预测服务
- `web_dashboard.py` - Web监控面板

## 使用方法

```bash
# 运行主程序
cd examples
python main.py

# 启动连续预测
python continuous_prediction.py

# 启动Web面板
python web_dashboard.py
```

## 依赖说明

所有示例程序都依赖于 `src/` 目录下的核心模块，请确保：
1. 已安装所有依赖包 (`pip install -r requirements.txt`)
2. 已配置API密钥和参数
3. 数据库文件存在于 `data/` 目录
