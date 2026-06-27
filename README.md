# 盈灵创意

> AI 图片/视频生成 + 通用 AI 对话 SaaS 平台 — 三合一完整项目，全本地部署。

## 🚀 快速开始

```bash
git clone https://github.com/shaoyunhao0107/yinglingchaungyi.git
cd yinglingchaungyi
cp .env.example .env   # 编辑填密钥
docker compose up -d --build
```

浏览器打开 `http://localhost:8000`

## 📦 三大模块

| 模块 | 端口 | 语言 | 功能 |
|------|------|------|------|
| **jimeng-saas** | 8000 | Python (FastAPI) | 主 SaaS 平台 |
| **jimeng-api** | 5100 | Node.js | 即梦 AI 逆向 API |
| **monica-proxy** | 8080 | Go | AI 对话代理（23 模型） |

## ✨ 功能

### 图片/视频生成
- 即梦 7 个图片模型 + 11 个视频模型 + 盈灵新版
- 自定义生图 API（UI 添加，OpenAI 兼容）
- 批量生成、媒体库、文件夹/标签/搜索

### AI 对话
- Monica Proxy 23 个模型（GPT/Claude/Gemini/Grok）
- 自定义大模型 API（GLM/DeepSeek/Claude 等，OpenAI + Anthropic 协议）
- 多会话持久化、置顶、搜索、Markdown 渲染、流式响应

### 管理
- 凭证池（即梦 sessionid + Monica cookie + 生图/对话 API 端点）
- 用户系统（credits、套餐、API Key、权限隔离）
- 审计日志、系统健康监控

## 📄 部署文档

| 方式 | 文档 | 适合 |
|------|------|------|
| **Docker Compose** | [DEPLOYMENT_DOCKER.md](DEPLOYMENT_DOCKER.md) | 一键部署，推荐 |
| **Windows 物理机** | [jimeng-saas/DEPLOYMENT_WINDOWS.md](jimeng-saas/DEPLOYMENT_WINDOWS.md) | 开发环境 |
| **Ubuntu 物理机** | [jimeng-saas/DEPLOYMENT_UBUNTU.md](jimeng-saas/DEPLOYMENT_UBUNTU.md) | 生产服务器 |

## 🗂 项目结构

```
yinglingchaungyi/
├── docker-compose.yml        # 全栈编排（6 服务）
├── .env.example              # 环境变量模板
├── start.bat / stop.bat      # Windows 一键启动/停止
├── jimeng-saas/              # 主应用
├── jimeng-api-external/      # 即梦 API
└── monica-proxy-master/      # 对话代理
```

## 🔧 配置

所有配置通过 UI 管理（凭证池页面），无需改配置文件：
- 即梦 sessionid → 凭证池
- Monica cookie → 凭证池 → Monica Proxy 配置
- 生图 API → 凭证池 → 生图 API 端点
- 对话 API → 凭证池 → 对话 API 端点

## License

MIT
