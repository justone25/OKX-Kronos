# 🔌 Kronos端口配置说明

## 📋 端口变更概述

为了避免与你现有服务器上的服务冲突，特别是已被占用的5000端口和可能被占用的80端口，我们对Kronos系统的端口配置进行了调整。

## 🔄 端口映射对比

| 服务 | 原端口 | 新端口 | 说明 |
|------|--------|--------|------|
| **Nginx反向代理** | 80 | 8081 | 对外暴露的主端口 |
| **Flask Web应用** | 5000 | 8080 | 内部应用端口 |
| **PostgreSQL** | 5432 | 5432 | 数据库端口（可选暴露） |
| **Redis** | 6379 | 6379 | 缓存端口（可选暴露） |

## 🏗️ 架构图（更新后）

```
外部访问 (OpenResty) → 127.0.0.1:8081 (Nginx) → 127.0.0.1:8080 (Flask)
                                    ↓
                            PostgreSQL:5432 + Redis:6379
```

## 📝 配置文件变更

### 1. Dockerfile
```dockerfile
# 变更前
EXPOSE 80 5000

# 变更后  
EXPOSE 8081
```

### 2. docker-compose.yml
```yaml
# 变更前
ports:
  - "80:80"
  - "5000:5000"

# 变更后
ports:
  - "8081:8081"
```

### 3. nginx.conf
```nginx
# 变更前
server {
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:5000;
    }
}

# 变更后
server {
    listen 8081;
    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

### 4. supervisord.conf
```ini
# 变更前
command=gunicorn --bind 0.0.0.0:5000 ...

# 变更后
command=gunicorn --bind 0.0.0.0:8080 ...
```

## 🌐 OpenResty集成配置

### 方案1：独立域名
```nginx
# 在你的OpenResty配置中添加
upstream kronos_backend {
    server 127.0.0.1:8081;
    keepalive 32;
}

server {
    listen 80;
    server_name kronos.yourdomain.com;
    
    location / {
        proxy_pass http://kronos_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 方案2：子路径
```nginx
# 在你现有的server块中添加
server {
    listen 80;
    server_name yourdomain.com;
    
    # 其他现有配置...
    
    # Kronos预测系统
    location /kronos/ {
        rewrite ^/kronos/(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Script-Name /kronos;
    }
    
    # API请求
    location /kronos/api/ {
        rewrite ^/kronos/(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Script-Name /kronos;
    }
}
```

## 🔍 端口检查命令

### 部署前检查
```bash
# 检查端口是否被占用
netstat -tlnp | grep :8081
netstat -tlnp | grep :8080
netstat -tlnp | grep :5432
netstat -tlnp | grep :6379

# 或使用ss命令
ss -tlnp | grep :8081
```

### 部署后验证
```bash
# 检查Kronos服务端口
curl -I http://localhost:8081/health

# 检查内部Flask应用
curl -I http://localhost:8080/api/system_status

# 检查数据库连接
docker-compose exec postgres pg_isready -U kronos

# 检查Redis连接
docker-compose exec redis redis-cli ping
```

## 🚨 故障排除

### 端口冲突问题
如果8081端口也被占用，可以修改为其他端口：

1. **修改docker-compose.yml**：
   ```yaml
   ports:
     - "8082:8081"  # 使用8082作为外部端口
   ```

2. **更新OpenResty配置**：
   ```nginx
   proxy_pass http://127.0.0.1:8082;
   ```

### 防火墙配置
```bash
# 如果使用ufw
sudo ufw allow 8081

# 如果使用iptables
sudo iptables -A INPUT -p tcp --dport 8081 -j ACCEPT
```

## 📊 性能优化建议

### OpenResty配置优化
```nginx
upstream kronos_backend {
    server 127.0.0.1:8081 max_fails=3 fail_timeout=30s;
    keepalive 32;
    keepalive_requests 100;
    keepalive_timeout 60s;
}

server {
    # 启用gzip压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    
    # 缓存静态文件
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg)$ {
        proxy_pass http://kronos_backend;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }
    
    # API请求限流
    limit_req_zone $binary_remote_addr zone=kronos_api:10m rate=10r/s;
    location /api/ {
        limit_req zone=kronos_api burst=20 nodelay;
        proxy_pass http://kronos_backend;
    }
}
```

## 🔐 安全配置

### SSL/TLS配置（推荐）
```nginx
server {
    listen 443 ssl http2;
    server_name kronos.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # SSL安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;
    
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header X-Forwarded-Proto https;
    }
}

# HTTP重定向到HTTPS
server {
    listen 80;
    server_name kronos.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

## 📋 部署检查清单

- [ ] 确认8081端口未被占用
- [ ] 确认8080端口未被占用  
- [ ] 更新OpenResty配置文件
- [ ] 重载OpenResty配置：`nginx -s reload`
- [ ] 启动Kronos服务：`docker-compose up -d`
- [ ] 验证服务可访问：`curl http://localhost:8081/health`
- [ ] 验证代理正常：`curl http://yourdomain.com/kronos/health`
- [ ] 检查日志无错误：`docker-compose logs -f`

## 🎯 访问地址总结

### 直接访问
- **Web界面**: `http://your-server-ip:8081`
- **API接口**: `http://your-server-ip:8081/api/`
- **健康检查**: `http://your-server-ip:8081/health`

### 通过OpenResty代理访问
- **独立域名**: `http://kronos.yourdomain.com`
- **子路径**: `http://yourdomain.com/kronos/`
- **API接口**: `http://yourdomain.com/kronos/api/`

---

✅ **端口配置完成后，Kronos系统将与你现有的服务完美共存，不会产生任何端口冲突！**
