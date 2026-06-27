# 盈灵创意 SaaS — Ubuntu 完整部署指南

> 本指南面向 Ubuntu 22.04 LTS / 24.04 LTS。覆盖 `jimeng-saas` + `jimeng-api` + `monica-proxy` 三个服务的物理机部署，全部用 systemd + nginx 管理，不依赖 Docker。

---

## 目录

1. [架构与服务总览](#1-架构与服务总览)
2. [系统环境要求](#2-系统环境要求)
3. [安装基础软件](#3-安装基础软件)
4. [克隆代码仓库](#4-克隆代码仓库)
5. [配置 PostgreSQL](#5-配置-postgresql)
6. [配置 Redis](#6-配置-redis)
7. [编译 monica-proxy](#7-编译-monica-proxy)
8. [配置 jimeng-api](#8-配置-jimeng-api)
9. [配置 jimeng-saas（.env）](#9-配置-jimeng-saas-env)
10. [初始化数据库 + 管理员账号](#10-初始化数据库--管理员账号)
11. [systemd 服务文件](#11-systemd-服务文件)
12. [Nginx 反向代理](#12-nginx-反向代理)
13. [配置即梦凭证](#13-配置即梦凭证)
14. [配置 Monica cookie](#14-配置-monica-cookie)
15. [验证清单](#15-验证清单)
16. [常见问题](#16-常见问题)

---

## 1. 架构与服务总览

| 服务 | 端口 | 说明 |
|---|---|---|
| `jimeng-saas` (web) | 8000 | FastAPI 主应用，对外入口 |
| `jimeng-saas` (worker) | — | RQ 异步任务消费者 |
| `jimeng-api` | 5100 | 即梦 AI 逆向 API（Node.js） |
| `monica-proxy` | 8080 | Monica 通用 AI 对话代理（Go） |
| PostgreSQL | 5432 | 主数据库 |
| Redis | 6379 | 任务队列 |
| Nginx | 80 | 反向代理，对外入口 |

**启动顺序**：postgresql → redis → jimeng-api → monica-proxy → jimeng-saas web → jimeng-saas worker

---

## 2. 系统环境要求

- Ubuntu 22.04 LTS 或 24.04 LTS
- 2 核 CPU / 4 GB 内存 / 20 GB 磁盘起步
- root 或具备 sudo 权限的普通用户
- 中国大陆服务器需要可用的 HTTP 代理（Clash/Mihomo，默认 `http://127.0.0.1:7897`）

---

## 3. 安装基础软件

### 3.1 更新系统

```bash
# 更新 apt 索引和已安装包
sudo apt update && sudo apt upgrade -y
```

### 3.2 安装 Python 3 + venv + pip

```bash
# 系统自带 Python 3.10/3.12，需要 venv 和 pip
sudo apt install -y python3 python3-pip python3-venv python3-dev

# 验证
python3 --version        # 应输出 3.10+ 或 3.12+
python3 -m venv --help   # 不报错即可
```

### 3.3 安装 PostgreSQL 16

```bash
# Ubuntu 22.04 默认仓库只有 PG 14，需要加官方仓库
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
sudo sh -c 'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'

sudo apt update
sudo apt install -y postgresql-16 postgresql-client-16 libpq-dev

# 验证
sudo -u postgres psql -c "SELECT version();"   # 应输出 postgresql 16.x
```

### 3.4 安装 Redis

```bash
sudo apt install -y redis-server

# 启动并设为开机自启
sudo systemctl enable --now redis-server

# 验证
redis-cli ping          # 应返回 PONG
```

### 3.5 安装 Node.js 18 LTS

```bash
# 加 NodeSource 仓库
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# 验证
node --version          # 应输出 v18.x
npm --version           # 应输出 9.x 或 10.x
```

### 3.6 安装 Go 1.25+

```bash
# 官方下载（可能需要代理）
cd /tmp
# 中国大陆可改用 https://golang.google.cn/dl/go1.25.0.linux-amd64.tar.gz
wget https://go.dev/dl/go1.25.0.linux-amd64.tar.gz

# 解压到 /usr/local
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go1.25.0.linux-amd64.tar.gz

# 加入 PATH（写入 ~/.bashrc 或 /etc/profile.d/go.sh）
echo 'export PATH=$PATH:/usr/local/go/bin' | sudo tee /etc/profile.d/go.sh
source /etc/profile.d/go.sh

# 验证
go version              # 应输出 go1.25.0 linux/amd64
```

### 3.7 安装 Nginx + Git + 构建工具

```bash
sudo apt install -y nginx git build-essential
```

---

## 4. 克隆代码仓库

约定目录 `/opt`：

```bash
sudo mkdir -p /opt
sudo chown $USER:$USER /opt

# 1) jimeng-saas 主应用
cd /opt
git clone https://github.com/<your-org>/jimeng-saas.git

# 2) jimeng-api（即梦逆向 API，源码：github.com/iptag/jimeng-api）
git clone https://github.com/iptag/jimeng-api.git jimeng-api-external

# 3) monica-proxy（通用 AI 对话代理）
git clone https://github.com/<your-org>/monica-proxy.git monica-proxy-master

# 验证
ls -d /opt/jimeng-saas /opt/jimeng-api-external /opt/monica-proxy-master
```

---

## 5. 配置 PostgreSQL

### 5.1 创建数据库用户和库

```bash
# 切到 postgres 用户执行
sudo -u postgres psql <<'SQL'
-- 创建应用专用用户（密码可自定义，需要与 .env 中 JSA_DB_URL 一致）
CREATE USER jsa WITH PASSWORD 'jsa_pass_2026';

-- 创建数据库，owner 是 jsa
CREATE DATABASE jimeng_saas OWNER jsa ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0;

-- 授权
GRANT ALL PRIVILEGES ON DATABASE jimeng_saas TO jsa;
SQL
```

### 5.2 调整 pg_hba.conf（允许密码登录）

```bash
# 找到配置文件位置
sudo -u postgres psql -tAc "SHOW hba_file"
# 一般是 /etc/postgresql/16/main/pg_hba.conf

# 确保包含下面这一行（用 scram-sha-256）
echo 'host    jimeng_saas    jsa    127.0.0.1/32    scram-sha-256' | sudo tee -a /etc/postgresql/16/main/pg_hba.conf

# 重载配置
sudo systemctl reload postgresql
```

### 5.3 验证连接

```bash
# 用 jsa 身份连接测试
PGPASSWORD=jsa_pass_2026 psql -h 127.0.0.1 -U jsa -d jimeng_saas -c "SELECT current_user, current_database();"
# 应输出：jsa | jimeng_saas
```

---

## 6. 配置 Redis

Ubuntu apt 装完默认监听 `127.0.0.1:6379`，**生产环境需要设密码**：

```bash
# 编辑配置
sudo sed -i 's/^# requirepass .*/requirepass your_redis_password_2026/' /etc/redis/redis.conf

# 重启生效
sudo systemctl restart redis-server

# 验证（带密码）
redis-cli -a your_redis_password_2026 ping
# 应返回 PONG
```

> 不设密码时，`.env` 中 `JSA_REDIS_URL=redis://localhost:6379/0` 即可。
> 设密码时改为 `redis://:your_redis_password_2026@localhost:6379/0`。

---

## 7. 编译 monica-proxy

### 7.1 解决 IPv6 + Go 模块代理问题（中国大陆必看）

国内服务器直连 `proxy.golang.org` 会失败或卡在 IPv6，必须显式走代理 + 国内 GOPROXY 镜像：

```bash
# 临时为本次 shell 设置代理（Clash/Mihomo 默认端口）
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897

# 让 go 走国内镜像
go env -w GOPROXY=https://goproxy.cn,direct
go env -w GOTOOLCHAIN=go1.25.0

# 关闭 CGO（编译出可移植的静态二进制）
go env -w CGO_ENABLED=0
```

### 7.2 编译

```bash
cd /opt/monica-proxy-master

# 拉取依赖
go mod download

# 编译（注意：源码 main.go 在根目录）
CGO_ENABLED=0 go build -ldflags "-s -w" -o monica-proxy main.go

# 验证
./monica-proxy --version || ls -lh monica-proxy
```

> 如果 `go mod download` 卡住：确认 `HTTPS_PROXY` 已 export，且 7897 端口的 Clash 在跑。
> `make build` 也行，但直接 `go build main.go` 更直观。

### 7.3 生成 bearer token

```bash
# 生成 32 字节随机 token，写入 config.yaml 的 security.bearer_token
openssl rand -hex 32
# 例：a1b2c3... 记下来，后面 .env 里 JSA_MONICA_PROXY_TOKEN 要用同一个
```

### 7.4 写 config.yaml

```bash
cd /opt/monica-proxy-master
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，关键字段：

```yaml
server:
  host: "127.0.0.1"      # 只对本机，由 nginx 反代对外
  port: 8080

monica:
  cookie: "YOUR_MONICA_COOKIE_HERE"   # 见第 14 节填法

security:
  bearer_token: "上一步生成的32字节hex"
  tls_skip_verify: true
```

---

## 8. 配置 jimeng-api

```bash
cd /opt/jimeng-api-external

# 安装依赖
npm install

# 编译 TypeScript -> dist/
npm run build

# 验证编译产物
ls dist/index.js
```

### 8.1 启动配置

`jimeng-api` 通过环境变量 `PORT` 监听端口，默认 5100。无需 `.env` 文件。
即梦账号通过 `sessionid` Cookie 注入，**不需要在这里配置账号**，由 `jimeng-saas` 在 `/admin/credentials` 页面维护。

---

## 9. 配置 jimeng-saas（.env）

### 9.1 创建 Python 虚拟环境

```bash
cd /opt/jimeng-saas

python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

### 9.2 生成密钥

```bash
# JWT 签名密钥
python -c "import secrets; print(secrets.token_urlsafe(48))"

# Fernet 加密密钥（用于加密即梦凭证池）
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 9.3 写 .env 文件

```bash
cd /opt/jimeng-saas
cp .env.example .env
```

完整字段表：

| 变量 | 示例值 | 说明 |
|---|---|---|
| `JSA_ENV` | `prod` | 运行环境 |
| `JSA_SECRET_KEY` | `步骤 9.2 第一行输出` | JWT 签名，至少 32 字符 |
| `JSA_MASTER_KEY` | `步骤 9.2 第二行输出` | Fernet 加密即梦凭证池 |
| `JSA_BASE_URL` | `http://localhost:8000` | 对外访问入口（线上改成你的域名） |
| `JSA_DB_URL` | `postgresql+psycopg2://jsa:jsa_pass_2026@127.0.0.1:5432/jimeng_saas` | PG 连接串 |
| `JSA_REDIS_URL` | `redis://localhost:6379/0` 或带密码 | Redis 连接串 |
| `JSA_STORAGE_BACKEND` | `local` | 存储后端 |
| `JSA_STORAGE_LOCAL_DIR` | `data/artifacts` | 本地存储路径 |
| `JSA_JIMENG_UPSTREAM` | `http://127.0.0.1:5100` | 即梦 API 上游 |
| `JSA_OPENAI_IMAGE_BASE_URL` | `http://your-image-server:port` | 盈灵新版图 API（可选） |
| `JSA_OPENAI_IMAGE_API_KEY` | `sk-xxxx` | 盈灵新版图 API Key（可选） |
| `JSA_MONICA_PROXY_BASE_URL` | `http://127.0.0.1:8080` | monica-proxy 地址 |
| `JSA_MONICA_PROXY_TOKEN` | `第 7.3 步生成的 hex` | 与 config.yaml 的 bearer_token 必须一致 |
| `JSA_ADMIN_EMAIL` | `admin@example.com` | 初始管理员邮箱 |
| `JSA_ADMIN_PASSWORD` | `admin123` | 初始管理员密码（生产请改强密码） |

`/opt/jimeng-saas/.env` 完整示例：

```ini
JSA_ENV=prod
JSA_SECRET_KEY=__粘贴步骤9.2第一个输出__
JSA_MASTER_KEY=__粘贴步骤9.2第二个输出__
JSA_BASE_URL=http://localhost:8000

JSA_DB_URL=postgresql+psycopg2://jsa:jsa_pass_2026@127.0.0.1:5432/jimeng_saas
JSA_REDIS_URL=redis://localhost:6379/0

JSA_STORAGE_BACKEND=local
JSA_STORAGE_LOCAL_DIR=data/artifacts

JSA_JIMENG_UPSTREAM=http://127.0.0.1:5100

JSA_OPENAI_IMAGE_BASE_URL=http://127.0.0.1:9000
JSA_OPENAI_IMAGE_API_KEY=sk-change-me

JSA_MONICA_PROXY_BASE_URL=http://127.0.0.1:8080
JSA_MONICA_PROXY_TOKEN=__粘贴步骤7.3生成的hex__

JSA_ADMIN_EMAIL=admin@example.com
JSA_ADMIN_PASSWORD=admin123
```

```bash
# 设置权限（只有部署用户可读）
chmod 600 /opt/jimeng-saas/.env
```

---

## 10. 初始化数据库 + 管理员账号

```bash
cd /opt/jimeng-saas
source .venv/bin/activate

# 1) 建表（创建所有 SQLAlchemy 模型对应的表）
python -c "from app.database import init_db; init_db()"

# 2) 种子初始管理员（读 .env 的 JSA_ADMIN_EMAIL / JSA_ADMIN_PASSWORD）
python scripts/seed_dev.py

# 验证管理员已建
PGPASSWORD=jsa_pass_2026 psql -h 127.0.0.1 -U jsa -d jimeng_saas \
  -c "SELECT id, email, role FROM users;"
# 应看到一行 admin@example.com / admin
```

---

## 11. systemd 服务文件

### 11.1 jimeng-api.service

```bash
sudo tee /etc/systemd/system/jimeng-api.service > /dev/null <<'EOF'
[Unit]
Description=Jimeng API (Node.js, port 5100)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/jimeng-api-external
Environment=PORT=5100
ExecStart=/usr/bin/node --enable-source-maps --no-node-snapshot dist/index.js
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### 11.2 monica-proxy.service

> 关键：必须把 `HTTP_PROXY` / `HTTPS_PROXY` 传给进程，否则 Go 的自定义 Transport 走不了 Clash 代理。

```bash
sudo tee /etc/systemd/system/monica-proxy.service > /dev/null <<'EOF'
[Unit]
Description=Monica Proxy (Go, port 8080)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/monica-proxy-master
# Monica API 在墙外，必须走 Clash/Mihomo
Environment=HTTP_PROXY=http://127.0.0.1:7897
Environment=HTTPS_PROXY=http://127.0.0.1:7897
ExecStart=/opt/monica-proxy-master/monica-proxy
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### 11.3 jimeng-saas.service（web）

```bash
sudo tee /etc/systemd/system/jimeng-saas.service > /dev/null <<'EOF'
[Unit]
Description=Jimeng SaaS Web (FastAPI uvicorn, port 8000)
After=network.target postgresql.service redis-server.service jimeng-api.service monica-proxy.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/jimeng-saas
EnvironmentFile=/opt/jimeng-saas/.env
ExecStart=/opt/jimeng-saas/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### 11.4 jimeng-saas-worker.service

```bash
sudo tee /etc/systemd/system/jimeng-saas-worker.service > /dev/null <<'EOF'
[Unit]
Description=Jimeng SaaS RQ Worker
After=network.target redis-server.service jimeng-saas.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/jimeng-saas
EnvironmentFile=/opt/jimeng-saas/.env
ExecStart=/opt/jimeng-saas/.venv/bin/python -m rq.cli worker jimeng --url redis://localhost:6379/0 --worker-class rq.worker.SimpleWorker
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### 11.5 启用并启动所有服务

```bash
# 重载 systemd 识别新服务
sudo systemctl daemon-reload

# 设置开机自启并立即启动
sudo systemctl enable --now jimeng-api
sudo systemctl enable --now monica-proxy
sudo systemctl enable --now jimeng-saas
sudo systemctl enable --now jimeng-saas-worker

# 一次性查看全部状态
systemctl status jimeng-api monica-proxy jimeng-saas jimeng-saas-worker --no-pager
```

---

## 12. Nginx 反向代理

### 12.1 配置文件

```bash
sudo tee /etc/nginx/sites-available/jimeng-saas > /dev/null <<'EOF'
# 监听 80，反代到 uvicorn 8000
server {
    listen 80;
    server_name _;            # 线上改成你的域名

    client_max_body_size 50M; # 上传图片允许 50MB

    # 主应用
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;             # 异步任务可能较慢
    }

    # WebSocket（如果用到了）
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
EOF
```

### 12.2 启用站点

```bash
# 启用站点
sudo ln -sf /etc/nginx/sites-available/jimeng-saas /etc/nginx/sites-enabled/

# 删除默认站点（避免冲突）
sudo rm -f /etc/nginx/sites-enabled/default

# 测试配置
sudo nginx -t

# 重载
sudo systemctl reload nginx
```

> 生产环境强烈建议加 HTTPS：`sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d your-domain.com`

---

## 13. 配置即梦凭证

登录 jimeng-saas 后台，把即梦账号录入系统：

1. 浏览器打开 `http://<server-ip>/admin/credentials`（或本机 `http://localhost:8000/admin/credentials`）
2. 用 `.env` 中配置的管理员账号登录（默认 `admin@example.com` / `admin123`）
3. 点击「添加凭证」，填入：
   - **名称**：方便区分，例如 `账号01`
   - **sessionid**：从即梦官网 cookie 取（见下方获取方法）
   - **其他可选字段**：按页面提示
4. 保存后系统会用 Fernet（`JSA_MASTER_KEY`）加密入库

### 即梦 sessionid 获取方法

1. 浏览器登录 https://jimeng.jianying.com
2. 按 `F12` 打开 DevTools → Application → Cookies → `https://jimeng.jianying.com`
3. 找到名为 `sessionid` 的 cookie，复制 Value 字段
4. 这就是 `jimeng-api` 调用即梦所需的凭证

---

## 14. 配置 Monica cookie

`monica-proxy` 通过 Monica.ai 的 cookie 调用 Claude/Gemini/Grok 等模型。

### 14.1 获取 cookie

1. 浏览器登录 https://monica.ai
2. `F12` → Application → Cookies → `https://monica.ai`
3. 复制整段 cookie（或关键字段，按 monica-proxy 的 README 说明）：
   - 通常需要 `sessionid` 或整段 `Cookie:` 头
4. 用 base64 / URL 编码检查无误后填入

### 14.2 写入 config.yaml

```bash
sudo nano /opt/monica-proxy-master/config.yaml
```

修改 `monica.cookie`：

```yaml
monica:
  cookie: "粘贴你的 Monica cookie 完整字符串"
```

### 14.3 重启 monica-proxy

```bash
sudo systemctl restart monica-proxy
```

### 14.4 验证 AI 对话可用

```bash
# 用 bearer_token 测试（token 来自 config.yaml 的 security.bearer_token）
TOKEN="__你的_bearer_token__"

curl -sS http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4",
    "messages": [{"role": "user", "content": "说一句你好"}]
  }'
# 应返回正常对话 JSON
```

---

## 15. 验证清单

按顺序 curl 各端口，全部通过即部署成功：

```bash
# 1. PostgreSQL（应返回版本号）
PGPASSWORD=jsa_pass_2026 psql -h 127.0.0.1 -U jsa -d jimeng_saas -tAc "SELECT version();"

# 2. Redis
redis-cli ping                                           # PONG

# 3. jimeng-api（应返回 200/JSON，不是 502）
curl -i http://127.0.0.1:5100/

# 4. monica-proxy（无 token 应返回 401，有 token 应能列模型）
curl -i http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer __你的_token__"

# 5. jimeng-saas web（应返回 200 + 登录页 HTML）
curl -i http://127.0.0.1:8000/

# 6. Nginx 入口（应反代到 web，返回 200）
curl -i http://127.0.0.1/

# 7. RQ worker 队列在线
redis-cli -n 0 LLEN rq:queue:jimeng                       # 0 或数字都正常
```

systemd 单元状态：

```bash
systemctl is-active postgresql redis-server jimeng-api monica-proxy jimeng-saas jimeng-saas-worker nginx
# 全部应该输出 active
```

---

## 16. 常见问题

### Q1：`sqlalchemy.exc.OperationalError: could not connect to server`

**原因**：`pg_hba.conf` 没有允许密码登录，或 PG 没监听 127.0.0.1。

**修复**：

```bash
# 检查监听
sudo ss -lntp | grep 5432

# 检查 pg_hba.conf 是否含 host jimeng_saas jsa 127.0.0.1/32 scram-sha-256
grep jsa /etc/postgresql/16/main/pg_hba.conf

# 确认 postgresql.conf 监听
grep "^listen_addresses" /etc/postgresql/16/main/postgresql.conf
# 应该是 listen_addresses = 'localhost' 或 '*'

sudo systemctl restart postgresql
```

### Q2：`redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379`

**原因**：Redis 没启动或绑在 IPv6 上。

**修复**：

```bash
sudo systemctl status redis-server
sudo ss -lntp | grep 6379
# 如果只监听 [::1]，修改 /etc/redis/redis.conf 中 bind 行为：
#   bind 127.0.0.1 ::1
sudo systemctl restart redis-server
```

### Q3：`go: golang.org/x/...: dial tcp: lookup proxy.golang.org: no such host`

**原因**：Go 模块下载没走代理。

**修复**：

```bash
# 必须在编译前 export 这两个变量
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
go env -w GOPROXY=https://goproxy.cn,direct
```

### Q4：`go mod download` 卡住或 IPv6 报错

**原因**：服务器 IPv6 路由异常，Go 默认优先走 v6。

**修复**：强制走 IPv4：

```bash
# 在编译 shell 中关闭 IPv6 解析优先
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1
sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1
```

或者继续开 IPv6 但让 Clash 走 v6，确保 Clash 配置允许 IPv6 入站。

### Q5：`ImportError: cannot import name 'bcrypt'` / `bcrypt version mismatch`

**原因**：`bcrypt>=4.1` 与某些 passlib 版本不兼容。

**修复**：

```bash
cd /opt/jimeng-saas
source .venv/bin/activate
pip install "bcrypt<4.1"
pip install --force-reinstall passlib
```

### Q6：登录后调用即梦报 `401 unauthorized`

**原因**：`jimeng-api` 的 `sessionid` 失效或未配置。

**修复**：去 `http://localhost:8000/admin/credentials` 重新添加有效的即梦 `sessionid`。`sessionid` 一般 7~14 天过期，需要定期更新。

### Q7：调用 monica-proxy 报 `401 unauthorized`

**原因**：`.env` 的 `JSA_MONICA_PROXY_TOKEN` 与 `config.yaml` 的 `security.bearer_token` 不一致。

**修复**：两边对齐，然后：

```bash
sudo systemctl restart monica-proxy jimeng-saas jimeng-saas-worker
```

### Q8：调用 monica-proxy 报 `502` 或超时

**原因**：Monica API 在墙外，systemd 单元没继承 `HTTP_PROXY` 环境变量。

**修复**：

```bash
# 确认 service 文件里有 Environment=HTTP_PROXY 和 HTTPS_PROXY
grep -E "HTTP_PROXY|HTTPS_PROXY" /etc/systemd/system/monica-proxy.service

sudo systemctl daemon-reload
sudo systemctl restart monica-proxy

# 验证进程是否带上了代理变量
cat /proc/$(pgrep -f monica-proxy | head -1)/environ | tr '\0' '\n' | grep -i proxy
```

### Q9：jimeng-api 启动报 `Cannot find module 'dist/index.js'`

**原因**：没执行 `npm run build`。

**修复**：

```bash
cd /opt/jimeng-api-external
npm install
npm run build
ls dist/index.js
sudo systemctl restart jimeng-api
```

### Q10：systemd 服务一直 `activating (auto-restart)`

看日志：

```bash
journalctl -u jimeng-saas -n 100 --no-pager
journalctl -u monica-proxy -n 100 --no-pager
journalctl -u jimeng-api -n 100 --no-pager
```

### Q11：RQ worker 不消费任务

```bash
# 看 worker 日志
journalctl -u jimeng-saas-worker -n 200 --no-pager

# 看 redis 队列
redis-cli LLEN rq:queue:jimeng
```

如果 `JSA_REDIS_URL` 带密码但 worker 命令行用了无密码 URL，会连不上 Redis。请同步 systemd 单元 `--url` 参数和 `.env` 的 `JSA_REDIS_URL`。
