# Jimeng SaaS — 本地原生部署指南（零 Docker）

完整的"打开浏览器就能用"流程。本机已配置好，但这份文档记录了所有步骤，方便你换机器或上线服务器时参考。

## 当前架构（无 Docker）

```
浏览器                     → http://127.0.0.1:8000
                             │
                             ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Web 服务 (Python, :8000)                   │
│   - 用户/认证/任务/媒体库/账单 全部路由             │
│   - Jinja2 + Alpine.js + HTMX 前端                  │
└─────────────────────────────────────────────────────┘
        │ enqueue                          ▲ SSE 轮询
        ▼                                  │
┌─────────────────────────────────────────────────────┐
│  RQ Worker (Python, 后台进程)                        │
│   - 消费 'jimeng' 队列                              │
│   - 调用 jimeng-api 下游                            │
│   - 下载/存储生成的图片视频                          │
└─────────────────────────────────────────────────────┘
        │                                  ▲
        ▼                                  │
┌──────────────────────────┐    ┌─────────────────────┐
│ RQ Queue (Memurai :6379) │    │ 本地文件存储         │
│  Redis-兼容 Windows 服务 │    │ data/artifacts/...   │
└──────────────────────────┘    └─────────────────────┘
        ▲
        │ HTTP 调用 /v1/images/generations 等
        │
┌─────────────────────────────────────────────────────┐
│  iptag/jimeng-api (Node.js, :5100)                  │
│   - 逆向工程即梦官方 API                            │
│   - 用 sessionid 作为 Bearer 认证                   │
│   - 上游：jimeng.jianving.com / dreamina.com        │
└─────────────────────────────────────────────────────┘
        │
        ▼
    即梦真实 API
```

## 一键启动

双击 `start_all.bat`。会开 3 个控制台窗口：jimeng-api、SaaS worker、SaaS web。
浏览器访问 `http://127.0.0.1:8000`。

停止：双击 `stop_all.bat`。

## 首次安装（本机已做，新机器才需要）

### 1. Memurai（Redis 替代）
```cmd
winget install Memurai.MemuraiDeveloper
:: 装完会自动注册成 Windows 服务，开机自启
:: 验证: "C:\Program Files\Memurai\memurai-cli.exe" ping  → PONG
```

### 2. Python 依赖
```cmd
"C:\Program Files\Python310\python.exe" -m pip install -r requirements.txt
:: 注意：bcrypt 必须是 4.x（passlib 不兼容 5.x），requirements.txt 已锁
```

### 3. jimeng-api 源码
```cmd
:: 克隆到项目外的目录（避免跟我们 SaaS 项目混淆）
cd \AI
git clone --depth 1 https://github.com/iptag/jimeng-api.git jimeng-api-external
cd jimeng-api-external
npm install --no-audit --no-fund
npm run build
```

### 4. 生成密钥 + 配置 .env
```cmd
:: 在 G:\AI\jimeng-saas 下创建 .env，包含：
python -c "from cryptography.fernet import Fernet; print('JSA_MASTER_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('JSA_SECRET_KEY=' + secrets.token_urlsafe(48))"

:: 把输出贴到 .env，参考 .env.example
```

### 5. 初始化 admin 用户
```cmd
python scripts\seed_dev.py
:: 输出: created admin id=1
```

## 获取即梦 sessionid（必填）

这是整个系统调用即梦真实 API 的凭证。**后端加密存储**，用户不会看到。

1. 浏览器打开 `https://jimeng.jianving.com`，登录你的账号
2. F12 打开开发者工具 → Application 标签 → 左侧 Cookies → 选 `https://jimeng.jianving.com`
3. 找到名为 `sessionid` 的 cookie，复制 **Value** 列的完整字符串
4. 浏览器打开 `http://127.0.0.1:8000/admin/credentials`
5. 区域选「国内站」，Session ID 粘贴刚才复制的值，备注写「主账号」之类
6. 点「添加到凭证池」

**国际站**（dreamina.com）：在 sessionid 前加前缀（区域选对应）：
- 美国站：`us-<sessionid>`
- 香港站：`hk-<sessionid>`
- 日本站：`jp-<sessionid>`
- 新加坡站：`sg-<sessionid>`

sessionid 会过期（通常几天到几周），过期后凭证池自动标记 `exhausted`，去 `/admin/credentials` 点「重置为健康」即可重新生效。

## 上线到生产服务器（Linux）

到这一步时项目已经在你的本地完全跑通，上线只是把同样的栈搬到 Linux（这次反而可以走 Docker，但也可继续原生）：

### 选项 A：继续原生（推荐，跟本地一致）
```bash
# 1. 装 Python 3.10 + Node 18+ + Redis + nginx
sudo apt install python3.10 python3-pip nodejs redis-server nginx

# 2. 拉两个仓库
git clone <你的 jsa 仓库>  /opt/jimeng-saas
git clone https://github.com/iptag/jimeng-api.git /opt/jimeng-api-external

# 3. 两个 Python venv（互不污染）
python3.10 -m venv /opt/jimeng-saas/.venv
/opt/jimeng-saas/.venv/bin/pip install -r /opt/jimeng-saas/requirements.txt

# 4. jimeng-api
cd /opt/jimeng-api-external && npm ci && npm run build

# 5. systemd unit（3 个：jsa-web、jsa-worker、jimeng-api）
# 模板见 systemd/*.service（我没生成，上线时再写）

# 6. nginx 反代 + Let's Encrypt
# /etc/nginx/sites-enabled/jsa:
#   location / { proxy_pass http://127.0.0.1:8000; }
#   location /api/jobs/stream { proxy_http_version 1.1; proxy_set_header Connection ""; }
```

### 选项 B：打包 Docker（SPEC 原计划）
项目里已有 `Dockerfile` + `docker-compose.yml`（4 服务：web+worker+redis+postgres）。
```
docker compose up -d
```
适合你不维护底层、要部署到 K8s/容器云的场景。

## 常见问题

**Q: 启动后访问 `/generate` 提交任务一直 `queued`？**
A: RQ worker 没起来。检查 `worker.bat` 那个窗口有没有错误。最常见是 Memurai 没启动 → 启动 Services (`services.msc`) 找 Memurai 启动。

**Q: 任务状态变成 `failed`，error 是 "即梦凭证无效或已过期"？**
A: sessionid 过期了。重新去 jimeng.com F12 取新的，到 `/admin/credentials` 添加或重置。

**Q: 想清掉所有数据从头开始？**
A: 停掉服务，删 `data/jimeng.db`（SQLite 文件），重跑 `seed_dev.py`。

**Q: Docker 真的完全不需要？**
A: 对，本地开发完全不需要。Memurai 替代 Redis、SQLite 替代 PostgreSQL、jimeng-api 直接 npm 跑替代 Docker 镜像。上线时如果想用容器，用现成的 `docker-compose.yml`。
