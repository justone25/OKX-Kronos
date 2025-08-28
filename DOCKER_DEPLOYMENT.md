# Docker部署指南

## 🐳 Docker环境部署

### 1. 准备配置文件

```bash
# 复制配置模板
cp config/.env.example config/.env

# 编辑配置文件，填入你的真实配置
vim config/.env
```

### 2. 重要配置项

确保在 `config/.env` 中设置正确的路径：

```bash
# 数据库配置（Docker容器内路径）
DATABASE_URL=sqlite:///app/data/predictions.db

# OKX API配置
OKX_API_KEY=your_real_api_key
OKX_SECRET_KEY=your_real_secret_key
OKX_PASSPHRASE=your_real_passphrase
```

### 3. Docker Compose 配置示例

```yaml
version: '3.8'
services:
  okx-kronos:
    build: .
    container_name: okx-kronos
    volumes:
      - ./data:/app/data          # 数据持久化
      - ./logs:/app/logs          # 日志持久化
      - ./config/.env:/app/config/.env  # 配置文件
    ports:
      - "8801:8801"               # Web面板端口
    environment:
      - PYTHONPATH=/app
    restart: unless-stopped
    entrypoint: ["/app/docker-entrypoint.sh"]
    command: ["python", "tools/kronos_launcher.py"]
```

### 4. 目录权限问题解决

如果遇到 "unable to open database file" 错误：

1. **检查目录权限**：
   ```bash
   ls -la data/
   chmod 755 data/
   ```

2. **使用Docker entrypoint**：
   项目已包含 `docker-entrypoint.sh` 脚本，会自动创建目录并设置权限

3. **手动创建目录**：
   ```bash
   mkdir -p data logs models
   chmod 755 data logs models
   ```

### 5. 常见问题

#### 问题1：数据库权限错误
```
ERROR - ❌ 表 predictions 初始化失败: unable to open database file
```

**解决方案**：
- 确保 `data` 目录存在且有写权限
- 检查Docker容器的用户权限
- 使用提供的 `docker-entrypoint.sh`

#### 问题2：模型下载失败
```
ERROR - ❌ 模型下载失败
```

**解决方案**：
- 检查网络连接
- 确保有足够的磁盘空间
- 检查 `models` 目录权限

#### 问题3：配置文件不存在
```
ERROR - 配置文件不存在
```

**解决方案**：
- 复制 `config/.env.example` 为 `config/.env`
- 填入真实的API配置

### 6. 启动命令

```bash
# 使用Docker Compose
docker-compose up -d

# 或直接使用Docker
docker run -d \
  --name okx-kronos \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config/.env:/app/config/.env \
  -p 8801:8801 \
  okx-kronos
```

### 7. 监控和日志

```bash
# 查看容器日志
docker logs -f okx-kronos

# 进入容器
docker exec -it okx-kronos bash

# 检查数据库
sqlite3 /app/data/predictions.db ".tables"
```

### 8. 数据备份

```bash
# 备份数据库
cp data/predictions.db data/predictions.db.backup

# 备份配置
cp config/.env config/.env.backup
```
