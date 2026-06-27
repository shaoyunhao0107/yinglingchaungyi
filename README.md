# 盈灵创意 — 统一管理目录

> 本目录聚合了盈灵创意 SaaS 的全部三个子项目，方便集中管理。

## 📂 目录结构

```
G:\AI\yinglingchaungyi├── jimeng-saas\            # 主 Web 应用（FastAPI）
├── jimeng-api-external\    # 即梦 AI 逆向 API（Node.js）
├── monica-proxy-master\    # 通用 AI 对话代理（Go）
├── start.bat               # ⭐ 一键启动全部
├── stop.bat                # ⭐ 一键停止全部
├── status.bat              # 查看服务状态
└── README.md               # 本文件
```

## 🚀 一键启动

**双击 `start.bat`**，会自动：

1. 检查 PostgreSQL 服务（自动启动）
2. 检查 Memurai (Redis) 服务（自动启动）
3. 开 4 个独立 cmd 窗口：
   - `jimeng-api (5100)` — 即梦 API
   - `monica-proxy (8080)` — AI 对话代理（带 Clash 代理）
   - `jimeng-saas worker` — RQ 异步任务
   - `jimeng-saas web (8000)` — Web 主应用

启动完成后浏览器打开 **http://localhost:8000**

## ⏹ 一键停止

**双击 `stop.bat`**

## 📊 查看状态

**双击 `status.bat`** — 看 5 个服务分别是否在跑

## 🔧 单独管理

| 操作 | 做法 |
|------|------|
| 重启 web | 关闭 `jimeng-saas web` 窗口，重新跑 `start.bat`（其他窗口保持） |
| 只重启 worker | 关闭对应窗口，在 jimeng-saas 目录手动跑 `worker.bat` |
| 改了 monica cookie | 编辑 `monica-proxy-master\config.yaml`，重启 monica-proxy 窗口 |
| 改了 .env | 重启 web + worker 两个窗口 |

## 🌐 服务端口

| 端口 | 服务 | 说明 |
|------|------|------|
| 8000 | jimeng-saas web | 主应用入口 |
| 5100 | jimeng-api | 即梦上游 |
| 8080 | monica-proxy | 对话代理 |
| 5432 | PostgreSQL | 数据库 |
| 6379 | Memurai | Redis 队列 |

## 📝 注意

- `jimeng-saas\.env` 含密钥，不要分享
- `monica-proxy-master\config.yaml` 含 Monica cookie，不要分享
- PostgreSQL 和 Memurai 是 Windows 服务，开机自启，不需要每次手动启动
- 改代码后需要重启对应窗口的服务才生效

## 🔗 上游仓库

- 主应用：https://github.com/shaoyunhao0107/yingling-chuangyi
- 即梦 API：https://github.com/iptag/jimeng-api
- 对话代理：https://github.com/ycvk/monica-proxy
