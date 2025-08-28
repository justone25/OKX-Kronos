# OKX-Kronos 安装指南

## 环境要求

- Python 3.8+
- pip 或 conda

## 安装步骤

### 1. 克隆项目
```bash
git clone <repository-url>
cd OKX-Kronos
```

### 2. 创建虚拟环境（推荐）
```bash
# 使用 venv
python -m venv kronos_env
source kronos_env/bin/activate  # Linux/Mac
# 或
kronos_env\Scripts\activate     # Windows

# 或使用 conda
conda create -n kronos python=3.9
conda activate kronos
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 配置环境变量
复制配置文件并填入你的API信息：
```bash
cp config/.env.example config/.env
```

编辑 `config/.env` 文件，填入：
- OKX API密钥信息
- 智谱AI API密钥
- 其他配置参数

### 5. 验证安装
```bash
python tools/kronos_launcher.py --help
```

## 常见问题

### 依赖安装失败
如果某些包安装失败，可以尝试：
```bash
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

### PyTorch安装问题
如果需要GPU支持，请访问 [PyTorch官网](https://pytorch.org/) 获取适合你系统的安装命令。

### OKX API配置
确保在OKX官网申请API密钥，并设置正确的权限：
- 读取权限：查看账户信息
- 交易权限：执行交易（如需要）

## 启动服务

### Web面板
```bash
python tools/kronos_launcher.py web
```

### 预测系统
```bash
python tools/kronos_launcher.py predict
```

## 目录结构
```
OKX-Kronos/
├── config/          # 配置文件
├── data/            # 数据存储
├── examples/        # 示例脚本
├── src/             # 源代码
├── static/          # Web静态文件
├── templates/       # Web模板
├── tools/           # 工具脚本
├── requirements.txt # 依赖列表
└── README.md        # 项目说明
```
