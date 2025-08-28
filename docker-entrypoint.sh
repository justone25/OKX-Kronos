#!/bin/bash

# Docker容器启动脚本
# 确保数据目录存在且有正确权限

set -e

echo "🐳 Docker容器启动中..."

# 创建必要的目录
echo "📁 创建数据目录..."
mkdir -p /app/data
mkdir -p /app/logs
mkdir -p /app/models

# 设置权限
echo "🔐 设置目录权限..."
chmod 755 /app/data
chmod 755 /app/logs
chmod 755 /app/models

# 检查配置文件
if [ ! -f "/app/config/.env" ]; then
    echo "⚠️ 配置文件不存在，复制模板..."
    cp /app/config/.env.example /app/config/.env
    echo "📝 请编辑 /app/config/.env 文件并填入你的配置"
fi

# 显示环境信息
echo "🔍 环境信息:"
echo "  工作目录: $(pwd)"
echo "  用户: $(whoami)"
echo "  用户ID: $(id -u)"
echo "  组ID: $(id -g)"
echo "  数据目录权限: $(ls -ld /app/data)"

# 执行传入的命令
echo "🚀 启动应用: $@"
exec "$@"
