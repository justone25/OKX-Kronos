# Git Worktree 版本管理指南

## 🎯 当前版本结构

我们使用Git Worktree来管理不同版本的OKX-Kronos项目：

```
/Users/littlecarp/PycharmProjects/
├── OKX-Kronos/           # 主开发目录 (main分支)
└── OKX-Kronos-v1.0/      # v1.0稳定版本 (v1.0-continuous-prediction分支)
```

## 📋 版本信息

### v1.0-continuous-prediction
- **功能**: 完整的持续预测系统
- **状态**: 稳定版本，生产就绪
- **特性**: Kronos AI模型 + 持续预测 + 监控面板
- **目录**: `../OKX-Kronos-v1.0/`

### main (开发版本)
- **功能**: 持续开发和新功能
- **状态**: 开发中
- **目录**: `./OKX-Kronos/`

## 🛠️ 使用方法

### 查看所有版本
```bash
git worktree list
```

### 切换到v1.0稳定版本
```bash
cd ../OKX-Kronos-v1.0

# 运行v1.0版本
./start_continuous.sh production
```

### 回到主开发版本
```bash
cd ../OKX-Kronos

# 继续开发新功能
```

### 在v1.0版本中查看状态
```bash
cd ../OKX-Kronos-v1.0
./start_continuous.sh status
```

## 🔄 版本管理操作

### 创建新版本分支
```bash
# 在主目录中
git branch v1.1-new-feature
git worktree add ../OKX-Kronos-v1.1 v1.1-new-feature
```

### 删除worktree
```bash
git worktree remove ../OKX-Kronos-v1.0
git branch -d v1.0-continuous-prediction
```

### 同步更改
```bash
# 在任意worktree中
git fetch origin
git pull origin <branch-name>
```

## 📊 版本对比

| 版本 | 目录 | 分支 | 状态 | 推荐用途 |
|------|------|------|------|----------|
| v1.0 | OKX-Kronos-v1.0 | v1.0-continuous-prediction | 稳定 | 生产运行 |
| main | OKX-Kronos | main | 开发 | 新功能开发 |

## 🎯 最佳实践

1. **生产使用**: 始终使用稳定版本 (v1.0)
2. **开发测试**: 在main分支进行新功能开发
3. **版本发布**: 完成新功能后创建新的版本分支
4. **数据隔离**: 每个版本使用独立的数据目录

## 🚀 快速启动

### 运行v1.0稳定版本
```bash
cd ../OKX-Kronos-v1.0
./start_continuous.sh production
```

### 开发新功能
```bash
cd ../OKX-Kronos
# 进行开发工作
```

## 📝 注意事项

1. **数据共享**: 两个版本可能共享某些数据文件
2. **配置文件**: 确保每个版本的配置正确
3. **端口冲突**: 避免同时运行多个版本
4. **依赖管理**: 每个版本可能需要不同的依赖

这样的版本管理方式让你可以：
- ✅ 稳定运行生产版本
- ✅ 安全开发新功能
- ✅ 快速切换版本
- ✅ 独立测试不同版本
