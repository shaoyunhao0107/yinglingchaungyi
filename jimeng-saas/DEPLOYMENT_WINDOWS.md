# 盈灵创意 SaaS — Windows 完整部署指南

> 面向 Windows 10/11 的物理机部署，**不需要 Docker**。三个服务全部原生跑，适合开发环境或小型办公服务器。

---

## 目录

1. [架构与服务总览](#1-架构与服务总览)
2. [系统环境要求](#2-系统环境要求)
3. [安装基础软件（winget）](#3-安装基础软件winget)
4. [克隆代码仓库](#4-克隆代码仓库)
5. [配置 PostgreSQL](#5-配置-postgresql)
6. [配置 Memurai（Redis 兼容）](#6-配置-memurairedis-兼容)
7. [编译 monica-proxy](#7-编译-monica-proxy)
8. [配置 jimeng-api](#8-配置-jimeng-api)
9. [配置 jimeng-saas 的 .env](#9-配置-jimeng-saas-的-env)
10. [初始化数据库 + 管理员](#10-初始化数据库--管理员)
11. [一键启动](#11-一键启动)
12. [配置即梦凭证](#12-配置即梦凭证)
13. [配置 Monica cookie](#13-配置-monica-cookie)
14. [验证清单](#14-验证清单)
15. [常见问题](#15-常见问题)

---

## 1. 架构与服务总览

| 服务 | 端口 | 可执行 | 启动方式 |
|---|---|---|---|
| jimeng-saas (web) | 8000 | python.exe | `uvicorn app.main:app` |
| jimeng-saas (worker) | — | python.exe | `rq.cli worker jimeng` |
| jimeng-api | 5100 | node.exe | `node dist/index.js` |
| monica-proxy | 8080 | monica-proxy.exe | Go 单二进制 |
| PostgreSQL | 5432 | postgres.exe | Windows 服务 |
| Memurai | 6379 | memurai.exe | Windows 服务 |

**启动顺序**：PostgreSQL → Memurai → jimeng-api → monica-proxy → jimeng-saas web → jimeng-saas worker

---

## 2. 系统环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Windows | 10/11 64-bit | Server 2019+ 也行 |
| Python | 3.10.x | 必须 3.10，不要用 Microsoft Store 版 |
| Node.js | 18 LTS+ | 跑 jimeng-api |
| PostgreSQL | 16+ | 主数据库 |
| Memurai | Developer（免费） | Redis 兼容 |
| Go | 1.25+ | 编译 monica-proxy |
| Git | 任意 | 克隆代码 |
| 内存 | 4 GB+ | 建议 8 GB |

**Clash/Mihomo（可选）**：中国大陆服务器需要代理走 Monica API，默认端口 7897。

---

## 3. 安装基础软件（winget）

```powershell
# 1. 打开 PowerShell（管理员权限）

# 2. 更新 winget 自身
winget upgrade winget

# 3. 一键安装全部依赖
winget install Python.Python.3.10
winget install PostgreSQL.Global.PostgreSQL.16
winget install Memurai.Memurai-Developer
winget install OpenJS.NodeJS.LTS
winget install GoLang.Go
winget install Git.Git

# 4. 关键：重启 PowerShell 让 PATH 生效
exit
```

**手动安装方式**（如果 winget 不可用）：
- Python: https://www.python.org/downloads/release/python-31011/
- PostgreSQL: https://www.postgresql.org/download/windows/
- Memurai: https://www.memurai.com/get-memurai
- Node.js: https://nodejs.org/
- Go: https://go.dev/dl/
- Git: https://git-scm.com/download/win

**验证安装**（新开 PowerShell）：

```powershell
python --version          # Python 3.10.x
node --version            # v18.x+
go version                # go1.25+
psql --version            # psql (PostgreSQL) 16+
memurai-cli --version     # Redis-compatible
git --version             # git version 2.x
```

---

## 4. 克隆代码仓库

```powershell
# 选一个盘（这里用 G:）
mkdir G:\AI -Force
cd G:\AI

# 克隆三个仓库
git clone https://github.com/shaoyunhao0107/jimeng-saas.git
git clone https://github.com/iptag/jimeng-api.git jimeng-api-external
git clone https://github.com/ycvk/monica-proxy.git monica-proxy-master
```

最终目录结构：
```
G:\AI\
├── jimeng-saas\            # 主应用
├── jimeng-api-external\    # 即梦 API
└── monica-proxy-master\    # 对话代理
```

---

## 5. 配置 PostgreSQL

### 5.1 启动 PostgreSQL 服务

如果安装包安装后服务名是 `postgresql-x64-16`：

```powershell
# 查看服务状态
Get-Service postgresql*

# 启动
Start-Service postgresql-x64-16

# 设为开机自启
Set-Service postgresql-x64-16 -StartupType Automatic
```

### 5.2 创建数据库用户和库

```powershell
# 用 postgres 超级用户登录（路径根据安装位置调整）
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres

# 在 psql 提示符里执行：
CREATE USER jsa WITH PASSWORD 'jsa_pass_2026';
CREATE DATABASE jimeng_saas OWNER jsa;
GRANT ALL PRIVILEGES ON DATABASE jimeng_saas TO jsa;
\q
```

### 5.3 验证连接

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U jsa -d jimeng_saas -c "SELECT 1;"
# 输出 1 即成功
```

> **坑**：PostgreSQL 服务重启后角色有时会消失（Windows 已知 bug）。如果突然连不上，重新执行 5.2 的 SQL。

---

## 6. 配置 Memurai（Redis 兼容）

Memurai 是 Redis 的 Windows 原生移植，免费 Developer 版够用。

```powershell
# 1. 安装后服务自启动
Get-Service Memurai*

# 2. 验证
memurai-cli ping
# 期望：PONG
```

**如果 memurai-cli 不在 PATH**，用完整路径：
```powershell
& "C:\Program Files\Memurai\memurai-cli.exe" ping
```

---

## 7. 编译 monica-proxy

### 7.1 编译

```powershell
cd G:\AI\monica-proxy-master

# 编译（Go 会自动下载依赖）
go build -o monica-proxy.exe main.go

# 验证
.\monica-proxy.exe --help
# 或者直接启动看是否正常
.\monica-proxy.exe
```

### 7.2 关键：IPv6 代理修复

monica-proxy 的 Go HTTP transport 默认不走代理，在中国大陆会因 IPv6 路由问题导致 Monica API 超时。

**修复方法**：编辑 `internal/utils/req_client.go`，在两处 `http.Transport{}` 里加 `Proxy` 字段：

```go
transport := &http.Transport{
    Proxy: http.ProxyFromEnvironment,   // ← 加这一行
    DialContext: ...
}
```

两处都加（createSSEClient 和 createDefaultClient），然后重新 `go build`。

### 7.3 配置 config.yaml

```powershell
# 复制示例
Copy-Item config.example.yaml config.yaml

# 编辑 config.yaml
notepad config.yaml
```

关键字段：

```yaml
monica:
  cookie: "session_id=eyJ0eXAi...你的完整 cookie"

security:
  bearer_token: "mytoken123"
  tls_skip_verify: true

server:
  host: "0.0.0.0"
  port: 8080
```

---

## 8. 配置 jimeng-api

```powershell
cd G:\AI\jimeng-api-external

# 安装依赖（首次 2-3 分钟）
npm install

# 编译 TypeScript
npm run build

# 验证：启动看是否监听 5100
npm start
# 看到 "listening on 5100" 即成功，Ctrl+C 先退出
```

---

## 9. 配置 jimeng-saas 的 .env

```powershell
cd G:\AI\jimeng-saas

# 生成密钥
python -c "from cryptography.fernet import Fernet; print('JSA_MASTER_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('JSA_SECRET_KEY=' + secrets.token_urlsafe(48))"
```

把输出填到 `.env`：

```powershell
# 创建 .env
notepad .env
```

完整内容：

```ini
JSA_ENV=prod
JSA_SECRET_KEY=改成你刚生成的 48 字符随机串
JSA_MASTER_KEY=改成你刚生成的 Fernet key

JSA_DB_URL=postgresql+psycopg2://jsa:jsa_pass_2026@localhost:5432/jimeng_saas
JSA_REDIS_URL=redis://localhost:6379/0

JSA_JIMENG_UPSTREAM=http://localhost:5100
JSA_MONICA_PROXY_BASE_URL=http://127.0.0.1:8080
JSA_MONICA_PROXY_TOKEN=mytoken123

JSA_ADMIN_EMAIL=admin@example.com
JSA_ADMIN_PASSWORD=改成强密码

JSA_BASE_URL=http://localhost:8000
JSA_STORAGE_BACKEND=local
JSA_STORAGE_LOCAL_DIR=data/artifacts
```

### 9.1 安装 Python 依赖

```powershell
cd G:\AI\jimeng-saas
pip install -r requirements.txt

# 关键：bcrypt 兼容
pip install "bcrypt<4.1"
```

---

## 10. 初始化数据库 + 管理员

```powershell
cd G:\AI\jimeng-saas

# 加载环境变量
Get-Content .env | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        Set-Variable -Name $Matches[1] -Value $Matches[2]
    }
}

# 建表
python -c "from app.database import init_db; init_db()"

# 创建管理员
python scripts\seed_dev.py
# 输出 admin@example.com / 你的密码
```

---

## 11. 一键启动

### 11.1 用 start_all.bat（推荐）

```powershell
cd G:\AI\jimeng-saas
.\start_all.bat
```

这会打开 **3 个 cmd 窗口**：
1. `jimeng-api (5100)` — 跑即梦 API
2. `SaaS worker (RQ)` — 跑异步任务消费
3. `SaaS web (8000)` — 跑 Web 主应用

### 11.2 手动启动 monica-proxy（需要 Clash 代理）

由于 `start_all.bat` 不包含 monica-proxy，需要单独启动：

```powershell
# 单独开一个 PowerShell 窗口
cd G:\AI\monica-proxy-master

# 关键：注入代理环境变量（Clash 在 7897）
$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"

.\monica-proxy.exe
```

或者直接用仓库里的 `start-all.ps1`（自动注入代理变量）：

```powershell
.\start-all.ps1
```

### 11.3 验证服务

```powershell
# Web
curl http://localhost:8000/health
# 期望：{"status":"ok","env":"prod"}

# jimeng-api
curl http://localhost:5100/

# monica-proxy
curl -H "Authorization: Bearer mytoken123" http://localhost:8080/v1/models
```

---

## 12. 配置即梦凭证

1. 浏览器访问 https://jimeng.jianying.com 并登录
2. F12 → Application → Cookies → https://jimeng.jianying.com
3. 复制 `sessionid` 的 Value
4. 打开 http://localhost:8000，用管理员登录
5. 进入「管理 → 凭证池」（/admin/credentials）
6. 区域选「cn」，粘贴 sessionid → 添加

---

## 13. 配置 Monica cookie

1. 浏览器访问 https://monica.im 并登录
2. F12 → Application → Cookies → https://monica.im
3. 复制 `session_id` 的 Value（eyJ... 开头的长串）
4. 编辑 `G:\AI\monica-proxy-master\config.yaml`
5. 把 cookie 粘到 `monica.cookie` 字段
6. 重启 monica-proxy 进程

---

## 14. 验证清单

逐项检查：

```powershell
# 1. PostgreSQL
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U jsa -d jimeng_saas -c "SELECT count(*) FROM users;"
# 应该至少有 1 个用户（admin）

# 2. Memurai (Redis)
memurai-cli ping

# 3. jimeng-api
curl http://localhost:5100/

# 4. monica-proxy
curl -H "Authorization: Bearer mytoken123" http://localhost:8080/v1/models | python -m json.tool

# 5. Web 健康
curl http://localhost:8000/health

# 6. Web 模型列表
$TOKEN = (curl -X POST http://localhost:8000/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email":"admin@example.com","password":"你的密码"}' `
  | ConvertFrom-Json).access

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/chat/models
# 应该返回 23 个模型

# 7. 浏览器
# 打开 http://localhost:8000 → 登录 → 仪表板 → 试试生图 → 试试 AI 对话
```

---

## 15. 常见问题

### Q1: 端口已被占用

```powershell
# 看占用
Get-NetTCPConnection -LocalPort 8000 -State Listen

# 杀进程
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force
}
```

### Q2: bcrypt 报错 `Error loading bcrypt`

```powershell
pip install "bcrypt<4.1"
pip install --force-reinstall passlib
```

### Q3: PostgreSQL 重启后角色消失

Windows 上 PostgreSQL 服务的已知 bug：

```powershell
# 用 postgres 超级用户重新创建
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE USER jsa WITH PASSWORD 'jsa_pass_2026';"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE jimeng_saas OWNER jsa;"
```

### Q4: monica-proxy 返回超时 / connection refused

Go 的自定义 Transport 不走系统代理。

**解决**：
1. 编辑 `internal/utils/req_client.go`，两处 Transport 加 `Proxy: http.ProxyFromEnvironment`
2. 重新 `go build -o monica-proxy.exe main.go`
3. 启动时带代理变量：`$env:HTTPS_PROXY = "http://127.0.0.1:7897"`

### Q5: heredoc / 脚本引号冲突

Windows PowerShell 和 bash 对引号处理不同。建议：
- 复杂命令写到 `.ps1` 文件里执行
- Python 脚本写到 `.py` 文件再跑

### Q6: CRLF 编码导致 shell 脚本报错

```powershell
# 用 Unix LF（git 自动处理）
git config --global core.autocrlf input
```

### Q7: RQ Worker 跑了但任务一直排队

检查 worker 是否真的连上 Redis：

```powershell
python -c "from redis import Redis; r = Redis.from_url('redis://localhost:6379/0'); print('Queue length:', r.llen('rq:queue:jimeng'))"
```

如果队列长度 > 0 但不消费，重启 worker 进程。

### Q8: 生成的图片看不到（403）

`/api/storage/` 需要鉴权。前端会自动加 token 参数。如果某些场景没加：

```javascript
// URL 应该带 token 参数
fetch(`/api/storage/${path}?token=${encodeURIComponent(accessToken)}`)
```

### Q9: Monica cookie 过期

Monica 的 session JWT 寿命较长（数月），但偶尔会失效。重新抓 cookie 更新 config.yaml。

### Q10: 如何开机自启

把以下脚本放到 `shell:startup`（Win+R 输入 `shell:startup`）：

```bat
@echo off
cd /d G:\AI\jimeng-saas
start "" cmd /c "start_all.bat"
timeout /t 5
cd /d G:\AI\monica-proxy-master
start "" powershell -NoProfile -Command "$env:HTTP_PROXY='http://127.0.0.1:7897'; $env:HTTPS_PROXY='http://127.0.0.1:7897'; .\monica-proxy.exe"
```

---

## 附录：完整启动流程速查

```powershell
# 一次性命令（首次部署）
cd G:\AI
git clone https://github.com/shaoyunhao0107/jimeng-saas.git
git clone https://github.com/iptag/jimeng-api.git jimeng-api-external
git clone https://github.com/ycvk/monica-proxy.git monica-proxy-master

cd jimeng-api-external; npm install; npm run build; cd ..
cd monica-proxy-master; go build -o monica-proxy.exe main.go; cd ..
cd jimeng-saas
pip install -r requirements.txt
pip install "bcrypt<4.1"
# 编辑 .env，填密钥
python -c "from app.database import init_db; init_db()"
python scripts/seed_dev.py

# 每次开机后的启动
cd G:\AI\jimeng-saas; .\start_all.bat
# 另开窗口
cd G:\AI\monica-proxy-master; .\start-all.ps1
```
