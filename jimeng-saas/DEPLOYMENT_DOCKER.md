# 盈灵创意 SaaS — Docker Compose 完整部署指南

> 一键启动 PostgreSQL + Redis + 即梦 API + Monica Proxy + Web + Worker 六个服务，适合 Linux/macOS/Windows 任何装了 Docker 的环境。

---

## 目录

1. [架构总览](#1-架构总览)
2. [前置要求](#2-前置要求)
3. [项目目录结构](#3-项目目录结构)
4. [克隆代码](#4-克隆代码)
5. [配置 jimeng-saas](#5-配置-jimeng-saas)
6. [配置 monica-proxy](#6-配置-monica-proxy)
7. [docker-compose.yml 完整内容](#7-docker-composeyml-完整内容)
8. [monica-proxy 的 Dockerfile](#8-monica-proxy-的-dockerfile)
9. [启动全部服务](#9-启动全部服务)
10. [初始化数据库 + 管理员](#10-初始化数据库--管理员)
11. [配置即梦凭证](#11-配置即梦凭证)
12. [验证清单](#12-验证清单)
13. [数据卷管理](#13-数据卷管理)
14. [升级流程](#14-升级流程)
15. [备份与恢复](#15-备份与恢复)
16. [常见问题](#16-常见问题)

---

## 1. 架构总览

| 服务 | 容器名 | 端口 | 说明 |
|---|---|---|---|
| `db` | jsa-db | 5432 → 5432 | PostgreSQL 16 数据库 |
| `redis` | jsa-redis | 6379 → 6379 | Redis 7 任务队列 |
| `jimeng-api` | jsa-jimeng-api | 5100 → 5100 | 即梦 AI 逆向 API（Node.js） |
| `monica-proxy` | jsa-monica-proxy | 8080 → 8080 | Monica 通用对话代理（Go） |
| `web` | jsa-web | 8002 → 8000 | FastAPI 主应用 |
| `worker` | jsa-worker | — | RQ 异步任务消费者 |

**启动顺序由 `depends_on` 自动管理**：db + redis → jimeng-api + monica-proxy → web + worker

---

## 2. 前置要求

- Docker 24.0+（含 Compose v2 插件）
- 2 核 CPU / 4 GB 内存 / 20 GB 磁盘
- 网络：能访问 GitHub（克隆代码）和 Docker Hub（拉镜像）

**中国大陆服务器**需要配置 Docker 镜像加速：
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

## 3. 项目目录结构

三个仓库**必须放在同级目录**，因为 docker-compose 会跨目录引用：

```
/opt/stack/
├── jimeng-saas/            # 主应用（含 docker-compose.yml）
│   ├── app/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env
│   └── ...
├── jimeng-api-external/    # 即梦 API（Node.js 源码）
│   ├── src/
│   ├── dist/
│   ├── package.json
│   └── ...
└── monica-proxy-master/    # 对话代理（Go 源码）
    ├── main.go
    ├── internal/
    ├── config.yaml
    ├── Dockerfile
    └── ...
```

---

## 4. 克隆代码

```bash
# 1. 创建根目录
sudo mkdir -p /opt/stack
sudo chown $USER:$USER /opt/stack
cd /opt/stack

# 2. 克隆三个仓库
git clone https://github.com/shaoyunhao0107/jimeng-saas.git
git clone https://github.com/iptag/jimeng-api.git jimeng-api-external
git clone https://github.com/ycvk/monica-proxy.git monica-proxy-master

# 3. 预编译 jimeng-api（容器内也会编译，但先 build 可加速）
cd jimeng-api-external
npm install && npm run build
cd ..

# 4. 准备 monica-proxy 配置（先复制示例）
cd monica-proxy-master
cp config.example.yaml config.yaml
# 编辑 config.yaml，填入 Monica cookie 和 bearer_token（见第 6 节）
cd ..
```

---

## 5. 配置 jimeng-saas

### 5.1 生成密钥

```bash
cd /opt/stack/jimeng-saas

# 生成 Fernet 主密钥（用于加密凭证池）
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 输出类似：Zmf8Kk3pX7vQ2W9eY1bN4rT6iU0oP5sA7dF1gH2jK3lM=

# 生成 JWT 密钥（32+ 字符随机串）
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# 输出类似：SUipMnKXAgIKgs4WIFgzywF3GFaMERj0uYzicRUBotorkQrKo0g8eHymcq-J4rF5
```

### 5.2 创建 .env

```bash
cat > .env <<'EOF'
# === 核心密钥（必须改） ===
JSA_ENV=prod
JSA_SECRET_KEY=改成你刚生成的 48 字符随机串
JSA_MASTER_KEY=改成你刚生成的 Fernet key

# === 数据库（容器内部服务名） ===
JSA_DB_URL=postgresql+psycopg2://jsa:jsa_pass_2026@db:5432/jimeng_saas
JSA_REDIS_URL=redis://redis:6379/0

# === 上游服务 ===
JSA_JIMENG_UPSTREAM=http://jimeng-api:5100
JSA_MONICA_PROXY_BASE_URL=http://monica-proxy:8080
JSA_MONICA_PROXY_TOKEN=mytoken123

# === 管理员 ===
JSA_ADMIN_EMAIL=admin@example.com
JSA_ADMIN_PASSWORD=请改成强密码

# === 其他 ===
JSA_BASE_URL=http://localhost:8002
JSA_STORAGE_BACKEND=local
JSA_STORAGE_LOCAL_DIR=data/artifacts
EOF
```

---

## 6. 配置 monica-proxy

### 6.1 编辑 config.yaml

```bash
cd /opt/stack/monica-proxy-master
vim config.yaml
```

**关键字段**：

```yaml
monica:
  # 从 monica.im 浏览器 cookie 复制（F12 → Application → Cookies → sessionid）
  cookie: "session_id=eyJ0eXAi...你的完整 cookie"

security:
  # 必须和 jimeng-saas 的 JSA_MONICA_PROXY_TOKEN 一致
  bearer_token: "mytoken123"
  tls_skip_verify: true

server:
  host: "0.0.0.0"
  port: 8080
```

### 6.2 获取 Monica cookie

1. 浏览器访问 https://monica.im 并登录
2. F12 → Application → Cookies → https://monica.im
3. 找到 `session_id` 那一项，**完整复制 Value**（eyJ... 开头的长串）
4. 粘到 config.yaml 的 cookie 字段：`cookie: "session_id=eyJ..."`

---

## 7. docker-compose.yml 完整内容

把以下内容写到 `/opt/stack/jimeng-saas/docker-compose.yml`：

```yaml
services:
  # ─── 数据库 ──────────────────────────
  db:
    image: postgres:16-alpine
    container_name: jsa-db
    environment:
      POSTGRES_USER: jsa
      POSTGRES_PASSWORD: jsa_pass_2026
      POSTGRES_DB: jimeng_saas
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U jsa -d jimeng_saas"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  # ─── Redis（队列 + 缓存）──────────────
  redis:
    image: redis:7-alpine
    container_name: jsa-redis
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  # ─── 即梦上游 API（Node.js）──────────
  jimeng-api:
    image: node:18-alpine
    container_name: jsa-jimeng-api
    working_dir: /app
    command: sh -c "npm install --no-audit --no-fund && npm run build && node dist/index.js"
    environment:
      PORT: 5100
    volumes:
      - ../jimeng-api-external:/app
      - jimeng_node_modules:/app/node_modules
    ports:
      - "5100:5100"
    restart: unless-stopped

  # ─── Monica Proxy（对话代理）─────────
  monica-proxy:
    build: ../monica-proxy-master
    container_name: jsa-monica-proxy
    environment:
      # 容器内不需要代理（容器走 Docker 网络）
      MONICA_COOKIE: ""
      BEARER_TOKEN: mytoken123
    volumes:
      - ../monica-proxy-master/config.yaml:/app/config.yaml:ro
    ports:
      - "8080:8080"
    restart: unless-stopped

  # ─── Web 服务（FastAPI）──────────────
  web:
    build: .
    image: jimeng-saas:latest
    container_name: jsa-web
    env_file: .env
    environment:
      # 覆盖 .env，用容器内部服务名
      JSA_DB_URL: postgresql+psycopg2://jsa:jsa_pass_2026@db:5432/jimeng_saas
      JSA_REDIS_URL: redis://redis:6379/0
      JSA_JIMENG_UPSTREAM: http://jimeng-api:5100
      JSA_MONICA_PROXY_BASE_URL: http://monica-proxy:8080
    volumes:
      - appdata:/app/data
    ports:
      - "8002:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      jimeng-api:
        condition: service_started
      monica-proxy:
        condition: service_started
    restart: unless-stopped

  # ─── Worker（异步任务）───────────────
  worker:
    image: jimeng-saas:latest
    container_name: jsa-worker
    command:
      - "python"
      - "-m"
      - "rq.cli"
      - "worker"
      - "jimeng"
      - "--url"
      - "redis://redis:6379/0"
      - "--worker-class"
      - "rq.worker.SimpleWorker"
    env_file: .env
    environment:
      JSA_DB_URL: postgresql+psycopg2://jsa:jsa_pass_2026@db:5432/jimeng_saas
      JSA_REDIS_URL: redis://redis:6379/0
      JSA_JIMENG_UPSTREAM: http://jimeng-api:5100
      JSA_MONICA_PROXY_BASE_URL: http://monica-proxy:8080
    volumes:
      - appdata:/app/data
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
  appdata:
  jimeng_node_modules:
```

---

## 8. monica-proxy 的 Dockerfile

写到 `/opt/stack/monica-proxy-master/Dockerfile`：

```dockerfile
# Stage 1: 编译
FROM golang:1.25-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o monica-proxy main.go

# Stage 2: 运行
FROM alpine:3.20
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /build/monica-proxy .
EXPOSE 8080
CMD ["./monica-proxy"]
```

---

## 9. 启动全部服务

```bash
cd /opt/stack/jimeng-saas

# 构建镜像 + 启动（首次约 3-5 分钟）
docker compose up -d --build

# 看实时日志
docker compose logs -f

# 看单个服务日志
docker compose logs -f web
docker compose logs -f worker
```

---

## 10. 初始化数据库 + 管理员

```bash
# 1. 建表（SQLModel 自动创建所有表）
docker compose exec web python -c "from app.database import init_db; init_db()"

# 2. 创建管理员账号
docker compose exec web python scripts/seed_dev.py
# 输出：Created admin admin@example.com / your_password
```

---

## 11. 配置即梦凭证

即梦 API 需要有效的 `sessionid` 才能真正调通文生图/视频。

### 获取 sessionid

1. 浏览器访问 https://jimeng.jianying.com 并登录
2. F12 → Application → Cookies → https://jimeng.jianying.com
3. 找到 `sessionid` 项，复制 Value

### 录入系统

1. 打开 `http://localhost:8002`，用管理员登录
2. 进入「管理 → 凭证池」（`/admin/credentials`）
3. 区域选「cn」（中国站直接粘贴；海外站加前缀 `us-` / `hk-` / `sg-`）
4. 粘贴 sessionid → 点「添加」
5. 系统会用 Fernet 加密入库

---

## 12. 验证清单

```bash
# 1. 所有容器在跑
docker compose ps
# 期望：6 个服务都是 Up 状态

# 2. Web 健康
curl http://localhost:8002/health
# 期望：{"status":"ok","env":"prod"}

# 3. jimeng-api 在线
curl http://localhost:5100/
# 期望：200 + HTML/JSON

# 4. monica-proxy 模型列表
curl -H "Authorization: Bearer mytoken123" http://localhost:8080/v1/models
# 期望：23 个模型的列表

# 5. 真实对话（需先登录拿 token）
TOKEN=$(curl -sX POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"你的密码"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access'])")

# 6. 创建对话
CONV=$(curl -sX POST http://localhost:8002/api/chat/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o"}')
echo $CONV  # 应该返回 id 字段

# 7. Web 浏览器
# 打开 http://localhost:8002 → 登录 → 看到「AI 对话」菜单 → 新建对话 → 发消息
```

---

## 13. 数据卷管理

```bash
# 查看所有卷
docker volume ls | grep jsa

# 卷 → 容器路径映射：
# pgdata              → db:/var/lib/postgresql/data      数据库数据
# redisdata           → redis:/data                      Redis AOF
# appdata             → web,worker:/app/data             用户上传/生成内容
# jimeng_node_modules → jimeng-api:/app/node_modules     Node 依赖缓存
```

**卷是持久化的**，`docker compose down` 不会删卷。只有 `docker compose down -v` 才会删卷（慎用）。

---

## 14. 升级流程

```bash
cd /opt/stack

# 1. 拉最新代码
cd jimeng-saas && git pull
cd ../jimeng-api-external && git pull && npm install && npm run build
cd ../monica-proxy-master && git pull
cd ../jimeng-saas

# 2. 重新构建 + 重启
docker compose up -d --build

# 3. 跑数据库迁移（如果有新表）
docker compose exec web python -c "from app.database import init_db; init_db()"
```

---

## 15. 备份与恢复

### 备份

```bash
# 备份数据库
docker compose exec db pg_dump -U jsa jimeng_saas > backup_$(date +%Y%m%d).sql

# 备份用户文件（生成的图片视频）
docker run --rm -v jsa_appdata:/data -v $(pwd):/backup alpine \
  tar czf /backup/appdata_$(date +%Y%m%d).tar.gz /data

# 备份 monica config
cp ../monica-proxy-master/config.yaml backup_monica_config_$(date +%Y%m%d).yaml
```

### 恢复

```bash
# 恢复数据库
cat backup_20260101.sql | docker compose exec -T db psql -U jsa jimeng_saas

# 恢复用户文件
docker run --rm -v jsa_appdata:/data -v $(pwd):/backup alpine \
  tar xzf /backup/appdata_20260101.tar.gz -C /
```

---

## 16. 常见问题

### Q1: `jimeng-api` 容器一直 restart

容器内每次启动都会 `npm install && npm run build`，如果源码有问题会循环失败。

**解决**：进入容器看日志
```bash
docker compose logs jimeng-api
docker compose exec jimeng-api sh
```

### Q2: `monica-proxy` 返回 401 invalid authorization

`.env` 的 `JSA_MONICA_PROXY_TOKEN` 和 `config.yaml` 的 `bearer_token` 不一致。

**解决**：两边对齐，重启：
```bash
docker compose restart monica-proxy web worker
```

### Q3: Web 返回 500 / `JSA_MASTER_KEY is not set`

`.env` 没正确加载，或 `JSA_MASTER_KEY` 还是 `CHANGE_ME_...`。

```bash
docker compose exec web env | grep JSA_MASTER
```

### Q4: 端口已被占用

```bash
# 看占用
sudo lsof -i :8002

# 改 docker-compose.yml 的端口映射
ports:
  - "8003:8000"   # 改成空闲端口
```

### Q5: 生图任务一直排队中

worker 没正常连 Redis。

```bash
# 看 worker 日志
docker compose logs worker

# 进 worker 测试 redis 连接
docker compose exec worker python -c "from redis import Redis; r=Redis.from_url('redis://redis:6379/0'); print(r.ping())"
```

### Q6: 内存不足（OOM）

PostgreSQL + Redis + Node + 2 个 Python 容器一起跑，至少要 4 GB 内存。

```bash
# 看内存占用
docker stats --no-stream

# 低内存机器（2GB）加 swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Q7: docker build 慢

配置镜像加速 + 用国内 npm 源：
```bash
# 在 jimeng-api 的 Dockerfile 加 ENV
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
```

### Q8: 升级后数据库表不对（新表没创建）

```bash
docker compose exec web python -c "from app.database import init_db; init_db()"
```

如果 schema 有冲突，看 `app/models/__init__.py` 是否 import 了新模型。
