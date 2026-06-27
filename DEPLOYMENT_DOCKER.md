# 盈灵创意 — Docker Compose 部署指南

> 一键启动全部 6 个服务，适合 Ubuntu / Debian / 任何装了 Docker 的 Linux。

---

## 目录

1. [架构总览](#1-架构总览)
2. [前置要求](#2-前置要求)
3. [克隆代码](#3-克隆代码)
4. [配置 .env](#4-配置-env)
5. [配置 Monica Cookie](#5-配置-monica-cookie)
6. [启动全部服务](#6-启动全部服务)
7. [初始化数据库](#7-初始化数据库)
8. [配置即梦凭证](#8-配置即梦凭证)
9. [验证清单](#9-验证清单)
10. [常用运维命令](#10-常用运维命令)
11. [升级流程](#11-升级流程)
12. [备份与恢复](#12-备份与恢复)
13. [常见问题](#13-常见问题)

---

## 1. 架构总览

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| db | ylc-db | 5432 | PostgreSQL 16 |
| redis | ylc-redis | 6379 | Redis 7（任务队列） |
| jimeng-api | ylc-jimeng-api | 5100 | 即梦 AI 逆向 API（Node.js） |
| monica-proxy | ylc-monica-proxy | 8080 | AI 对话代理（Go，23 个模型） |
| web | ylc-web | 8000 | FastAPI 主应用 |
| worker | ylc-worker | — | RQ 异步任务消费者 |

---

## 2. 前置要求

```bash
# Docker 24+ + Compose v2
docker --version          # Docker version 24+
docker compose version    # Docker Compose version v2.20+

# 磁盘：至少 10 GB（镜像 + 数据）
# 内存：至少 4 GB
```

**中国大陆服务器**加速 Docker Hub：
```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": ["https://docker.mirrors.ustc.edu.cn"]
}
EOF
sudo systemctl restart docker
```

---

## 3. 克隆代码

```bash
git clone https://github.com/shaoyunhao0107/yinglingchaungyi.git
cd yinglingchaungyi
```

目录结构：
```
yinglingchaungyi/
├── docker-compose.yml        # ← 全栈编排（6 服务）
├── .env.example              # ← 环境变量模板
├── jimeng-saas/              # 主应用（含 Dockerfile）
├── jimeng-api-external/      # 即梦 API（Node.js 源码）
└── monica-proxy-master/      # 对话代理（Go 源码 + Dockerfile）
```

---

## 4. 配置 .env

```bash
cp .env.example .env
nano .env
```

**必须修改的字段**：

```ini
# 生成密钥（在终端运行）：
# python3 -c "import secrets; print(secrets.token_urlsafe(48))"
JSA_SECRET_KEY=粘贴上面的输出

# 生成 Fernet 密钥：
# python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
JSA_MASTER_KEY=粘贴上面的输出

# 管理员密码
JSA_ADMIN_PASSWORD=改成强密码

# Monica Proxy 的 cookie（见下一节）
MONICA_COOKIE=session_id=eyJ0eXAi...你的完整cookie
MONICA_BEARER_TOKEN=mytoken123
```

其余字段保持默认即可（Docker 内部服务名已配好）。

---

## 5. 配置 Monica Cookie

Monica Proxy 需要 Monica.ai 的登录 cookie 才能调用 GPT/Claude/Gemini：

1. 浏览器打开 https://monica.im 并登录
2. F12 → Application → Cookies → https://monica.im
3. 找到 `session_id`，复制完整 Value（eyJ... 开头的长串）
4. 粘贴到 `.env` 的 `MONICA_COOKIE` 字段：

```ini
MONICA_COOKIE=session_id=eyJ0eXAiOiJKV1Qi...你的完整cookie值
```

> 也可以不配 cookie，启动后在「凭证池 → Monica Proxy 配置」面板里填。

---

## 6. 启动全部服务

```bash
docker compose up -d --build
```

首次构建约 5-10 分钟（Go 编译 + Node.js install + Python 依赖）。

看实时日志：
```bash
docker compose logs -f
```

单独看某个服务：
```bash
docker compose logs -f web
docker compose logs -f worker
docker compose logs -f monica-proxy
```

---

## 7. 初始化数据库

```bash
# 建表（SQLModel 自动创建所有表）
docker compose exec web python -c "from app.database import init_db; init_db()"

# 创建管理员账号
docker compose exec web python scripts/seed_dev.py
# 输出类似：Created admin admin@example.com / your_password
```

---

## 8. 配置即梦凭证

即梦生图需要有效的 sessionid：

1. 浏览器打开 https://jimeng.jianying.com 并登录
2. F12 → Application → Cookies → https://jimeng.jianying.com
3. 找到 `sessionid`，复制 Value
4. 打开 `http://localhost:8000`，用管理员登录
5. 进入「管理 → 凭证池」（/admin/credentials）
6. 区域选「cn」，粘贴 sessionid → 添加

---

## 9. 验证清单

```bash
# 1. 所有容器在跑
docker compose ps
# 期望：6 个服务都是 Up

# 2. Web 健康
curl http://localhost:8000/health
# 期望：{"status":"ok","env":"prod"}

# 3. jimeng-api
curl http://localhost:5100/

# 4. monica-proxy 模型列表
curl -H "Authorization: Bearer mytoken123" http://localhost:8080/v1/models | python3 -c "import sys,json; print(len(json.load(sys.stdin)['data']), 'models')"
# 期望：23 models

# 5. 浏览器
# 打开 http://localhost:8000 → 登录 → 仪表板
# 试生图（选即梦模型）
# 试 AI 对话（选 GPT/Claude 模型）
```

---

## 10. 常用运维命令

```bash
# 查看状态
docker compose ps

# 查看日志
docker compose logs -f web        # 实时跟踪
docker compose logs --tail 100 web  # 最后 100 行

# 重启某个服务
docker compose restart web
docker compose restart worker

# 停止全部
docker compose down

# 停止并删除数据卷（⚠️ 慎用，会丢数据）
docker compose down -v

# 进入容器调试
docker compose exec web bash
docker compose exec db psql -U jsa -d jimeng_saas
```

---

## 11. 升级流程

```bash
cd yinglingchaungyi
git pull

# 重新构建 + 重启
docker compose up -d --build

# 跑数据库迁移（如果有新表）
docker compose exec web python -c "from app.database import init_db; init_db()"
```

---

## 12. 备份与恢复

### 备份

```bash
# 备份数据库
docker compose exec db pg_dump -U jsa jimeng_saas > backup_$(date +%Y%m%d).sql

# 备份用户文件（生成的图片视频）
docker run --rm -v yinglingchaungyi_appdata:/data -v $(pwd):/backup alpine \
  tar czf /backup/appdata_$(date +%Y%m%d).tar.gz /data
```

### 恢复

```bash
# 恢复数据库
cat backup_20260101.sql | docker compose exec -T db psql -U jsa jimeng_saas

# 恢复用户文件
docker run --rm -v yinglingchaungyi_appdata:/data -v $(pwd):/backup alpine \
  tar xzf /backup/appdata_20260101.tar.gz -C /
```

---

## 13. 常见问题

### Q1: jimeng-api 容器一直 restart

容器内每次启动都 `npm install && npm run build`，如果源码有问题会循环失败。

```bash
docker compose logs jimeng-api
```

### Q2: monica-proxy 返回 401

`.env` 的 `MONICA_BEARER_TOKEN` 和 `JSA_MONICA_PROXY_TOKEN` 不一致。

### Q3: 生图任务一直排队

worker 没正确连 Redis：
```bash
docker compose logs worker
docker compose exec worker python -c "from redis import Redis; print(Redis.from_url('redis://redis:6379/0').ping())"
```

### Q4: 内存不足（OOM）

至少 4 GB 内存。低内存机器加 swap：
```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
```

### Q5: 端口冲突

改 `docker-compose.yml` 的端口映射：
```yaml
ports:
  - "8001:8000"   # 改成空闲端口
```

### Q6: Docker build 慢

```bash
# 用国内 npm 源（在 jimeng-api 的 Dockerfile 加 ENV）
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
```

### Q7: 升级后新表没创建

```bash
docker compose exec web python -c "from app.database import init_db; init_db()"
```
