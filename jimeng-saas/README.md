# 盈灵创意

> AI 图片/视频生成 + 通用 AI 对话 SaaS 平台 — 全本地部署，零强制依赖。

![Python](https://img.shields.io/badge/python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

## ✨ 三大核心模块

### 🎨 图片/视频生成（即梦逆向）
- **图片**：7 个即梦模型（盈灵 5.0/4.6/4.5/4.1/4.0/3.1/3.0）+ 盈灵新版（gpt-image-2）
- **视频**：Seedance 2.0 全系列 + 3.5 Pro / 3.0 Pro / 3.0 / 2.0 共 11 个模型
- **批量生成**：多提示词一次性入队，异步消费
- **媒体库**：文件夹、标签、搜索、回收站、批量管理

### 💬 AI 对话（Monica Proxy）
- **23 个模型**：GPT（5.5/5.4/4o/o3）、Claude（4-8 Opus/Sonnet 4-6）、Gemini（3.5 Flash/3.1 Pro）、Grok（4.3/4.2）
- **多会话管理**：DB 持久化、置顶、重命名、搜索、跨设备同步
- **流式响应**：SSE 实时输出，支持停止生成
- **Markdown 渲染**：代码块、表格、列表、引用全支持
- **思考链**：解析 `<think>` 标签，可切换显示/隐藏
- **快捷操作**：复制回复、重新生成

### 👤 用户系统
- 注册（默认 10 credits，free 套餐）
- 套餐升级（Stripe，支持 mock 模式）
- API Key 管理（仅管理员）
- 权限隔离（普通用户看不到管理面板/视频功能/API Key）

### 🛡️ 管理面板
- 凭证池管理（即梦 sessionid，Fernet 加密存储）
- 系统健康（Provider 状态、DB 连接、Redis 队列）
- 所有任务（跨用户查看）
- 审计日志

---

## 🏗️ 技术架构

```
用户浏览器
    │
    ▼
FastAPI (:8000) ← Jinja2 + Alpine.js + marked.js
    │
    ├─→ jimeng-api (:5100)   ─→ 即梦 AI（图片/视频）
    ├─→ monica-proxy (:8080) ─→ Monica AI（GPT/Claude/Gemini/Grok）
    │
    ├─→ PostgreSQL (:5432)   ─ 用户/作品/对话/凭证
    └─→ Redis (:6379)        ─ RQ 任务队列
                                 │
                                 ▼
                            RQ Worker（异步生成）
```

**三个独立服务**：
| 服务 | 端口 | 语言 | 作用 |
|---|---|---|---|
| jimeng-saas | 8000 | Python | 主 Web 应用 + Worker |
| jimeng-api | 5100 | Node.js | 即梦 AI 逆向 API |
| monica-proxy | 8080 | Go | 通用 AI 对话代理 |

---

## 🚀 快速开始

### 三种部署方式任选

| 方式 | 适合 | 文档 |
|---|---|---|
| **Docker Compose** | 一键部署，任何系统 | [DEPLOYMENT_DOCKER.md](DEPLOYMENT_DOCKER.md) |
| **Ubuntu 物理机** | 生产服务器，systemd 管理 | [DEPLOYMENT_UBUNTU.md](DEPLOYMENT_UBUNTU.md) |
| **Windows 物理机** | 开发环境，无 Docker | [DEPLOYMENT_WINDOWS.md](DEPLOYMENT_WINDOWS.md) |

### 最快上手（Docker，5 分钟）

```bash
# 1. 准备三个目录同级
git clone https://github.com/shaoyunhao0107/jimeng-saas.git
git clone https://github.com/iptag/jimeng-api.git jimeng-api-external
git clone https://github.com/ycvk/monica-proxy.git monica-proxy-master

# 2. 配置
cd jimeng-saas
cp .env.example .env
# 编辑 .env，填密钥和管理员密码

# 3. 配置 monica-proxy（详见 DEPLOYMENT_DOCKER.md）

# 4. 一键启动
docker compose up -d --build

# 5. 初始化
docker compose exec web python -c "from app.database import init_db; init_db()"
docker compose exec web python scripts/seed_dev.py

# 6. 打开浏览器
# http://localhost:8002
```

---

## 📂 项目结构

```
jimeng-saas/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # pydantic-settings 配置
│   ├── auth.py                 # JWT + bcrypt
│   ├── database.py             # SQLModel 引擎
│   ├── security.py             # Fernet 加密
│   ├── models/                 # SQLModel 表
│   │   ├── user.py             # User + QuotaEvent + ApiKey
│   │   ├── job.py              # GenerationJob
│   │   ├── artifact.py         # Artifact + ArtifactFolder + ArtifactTag
│   │   ├── credential.py       # ProviderCredential（Fernet 加密）
│   │   ├── chat.py             # ChatConversation + ChatMessage ⭐ 新
│   │   └── ...
│   ├── routes/
│   │   ├── auth.py             # 登录/注册/刷新
│   │   ├── jobs.py             # 生成任务提交
│   │   ├── artifacts.py        # 作品 CRUD + 存储
│   │   ├── admin.py            # 管理面板
│   │   ├── chat.py             # AI 对话 API ⭐ 新
│   │   ├── pages.py            # Jinja2 页面路由
│   │   └── ...
│   ├── providers/
│   │   ├── jimeng.py           # 即梦 provider（文生图/视频）
│   │   ├── openai_image.py     # OpenAI 图片 provider
│   │   └── registry.py         # provider 注册表
│   ├── worker/
│   │   ├── tasks.py            # RQ 任务定义
│   │   └── connection.py       # 队列连接
│   ├── services/
│   │   ├── quota.py            # credits 计费
│   │   ├── storage.py          # 本地/S3 存储
│   │   └── pool.py             # 凭证池轮询
│   ├── templates/              # Jinja2 模板
│   │   ├── base.html           # 全局 chrome + 菜单
│   │   ├── dashboard.html
│   │   ├── generate.html       # 生成画布
│   │   ├── library.html        # 媒体库
│   │   ├── chat.html           # AI 对话（Aurora 风格） ⭐ 新
│   │   └── ...
│   └── static/
│       ├── style.css           # Studio Dark 主题
│       └── vendor/
│           ├── alpine.min.js
│           ├── htmx.min.js
│           └── marked.min.js   # Markdown 渲染 ⭐ 新
├── scripts/
│   ├── seed_dev.py             # 初始化管理员
│   └── quota_reset_cron.py     # credits 重置定时
├── Dockerfile                  # Web + Worker 共用镜像
├── docker-compose.yml          # 全栈 6 服务编排
├── requirements.txt
├── run.bat / start_all.bat     # Windows 启动脚本
├── worker.bat                  # Windows worker 启动
├── .env.example
├── DEPLOYMENT_DOCKER.md        # Docker 部署指南
├── DEPLOYMENT_UBUNTU.md        # Ubuntu 部署指南
├── DEPLOYMENT_WINDOWS.md       # Windows 部署指南
└── README.md                   # 你正在看的这个
```

---

## 🔧 核心配置

### .env 字段速查

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `JSA_SECRET_KEY` | ✅ | — | JWT 签名密钥，32+ 字符随机串 |
| `JSA_MASTER_KEY` | ✅ | — | Fernet 加密密钥（加密凭证池） |
| `JSA_DB_URL` | ✅ | sqlite | PostgreSQL 连接串 |
| `JSA_REDIS_URL` | ✅ | redis://localhost:6379/0 | Redis 连接串 |
| `JSA_JIMENG_UPSTREAM` | ❌ | http://localhost:5100 | 即梦 API 地址 |
| `JSA_MONICA_PROXY_BASE_URL` | ❌ | http://127.0.0.1:8080 | Monica Proxy 地址 |
| `JSA_MONICA_PROXY_TOKEN` | ❌ | — | Monica Proxy Bearer token |
| `JSA_ADMIN_EMAIL` | ❌ | admin@local | 初始管理员邮箱 |
| `JSA_ADMIN_PASSWORD` | ❌ | admin123 | 初始管理员密码 |
| `JSA_OPENAI_IMAGE_BASE_URL` | ❌ | — | OpenAI 图片 API（可选） |

完整字段说明见 [.env.example](.env.example)。

---

## 🎨 设计系统

**Aurora 极光主题**（紫粉渐变 + 暗色背景）：
- 主色：`#8B5CF6 → #EC4899`（紫到粉）
- 背景：`#0a0a0c`（base）/ `#131316`（elevated）
- 字体：Cabinet Grotesk（标题）+ Plus Jakarta Sans（正文）+ JetBrains Mono（代码）
- 圆角：6/10/14/20px 四档
- 视觉特色：玻璃态、微光晕、非对称圆角、SVG 线条图标

---

## 📝 License

MIT

---

## 🤝 致谢

- [iptag/jimeng-api](https://github.com/iptag/jimeng-api) — 即梦 AI 逆向
- [ycvk/monica-proxy](https://github.com/ycvk/monica-proxy) — Monica 代理
- [FastAPI](https://fastapi.tiangolo.com/) — Web 框架
- [SQLModel](https://sqlmodel.tiangolo.com/) — ORM
- [Alpine.js](https://alpinejs.dev/) — 前端响应式
- [marked.js](https://marked.js.org/) — Markdown 渲染
