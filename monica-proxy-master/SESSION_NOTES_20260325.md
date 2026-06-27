# Monica Proxy 双协议项目 - 关键会话记录

记录时间：2026-03-25
项目路径：G:\AI\monica\monica-proxy-master
备份路径：G:\AI\monica\backups\monica-proxy-20260325-155006
Skill路径：C:\Users\admin\.openclaw\skills\monica-proxy-dualapi\

---

## 本次完成内容

### 1. OpenAI Responses API 兼容层
- 新增：`internal/apiserver/responses.go`
- 路由：`POST /v1/responses`
- 复用 `service.ChatService.HandleChatCompletion` + 转换函数 `chatCompletionToResponses`
- 流式暂返回 400（非流式完整实现）

### 2. Anthropic Messages API 兼容层
- 新增：`internal/apiserver/anthropic_compat.go`
- 路由：`POST /v1/messages`
- 支持非流式和流式
- 流式格式：`message_start / content_block_delta / message_stop`
- 非流式：转换为 Anthropic `anthropicOutMessage` 格式

### 3. 鉴权中间件兼容
- 修改：`internal/middleware/auth.go`
- 支持：
  - `Authorization: Bearer <token>`
  - `x-api-key: <token>`
  - `X-API-Key: <token>`
  - `api-key: <token>`
- 通过 reflect 从 Config struct 自动提取 token 字段

### 4. 路由注册（router.go）
```go
e.POST("/v1/chat/completions", ...) // 原有
e.POST("/v1/responses", createResponsesHandler(chatService))
e.POST("/v1/messages", createAnthropicCompatHandler(chatService))
```

### 5. Windows 本地备份
- 备份目录：G:\AI\monica\backups\monica-proxy-20260325-155006\
- 包含：windows + linux 二进制、ubuntu 脚本、文档
- 压缩包：G:\AI\monica\backups\monica-proxy-20260325-155006.zip

### 6. Ubuntu 部署文件
- `deploy/ubuntu/start.sh`
- `deploy/ubuntu/monica-proxy.service`
- `deploy/ubuntu/DUAL_API_DEPLOY.md`

### 7. Skill 封装
- `C:\Users\admin\.openclaw\skills\monica-proxy-dualapi\`
- 含：SKILL.md、references/*.md、scripts/build_and_backup.ps1

---

## 关键协议对接坑位（必看）

### 坑1：Cherry Studio Anthropic 提供商
- Cherry 使用 Anthropic 提供商时请求 `/v1/messages`（不是 `/v1/chat/completions`）
- 之前服务没有这个路由 → 404
- 解决：新增 `/v1/messages` 路由做协议转换

### 坑2：鉴权头不匹配
- Cherry Anthropic 提供商发送 `x-api-key` 头
- 原中间件只认 `Authorization: Bearer`
- 现象：401 Unauthorized
- 解决：auth.go 同时支持两种头

### 坑3：YAML cookie 解析
- cookie 字段含 `=; "` 等特殊字符
- 错误写法：`cookie: ""_fbp=...`（多余引号）
- 正确写法：`cookie: '_fbp=...; session_id=...'`（单引号包裹）

### 坑4：端口占用
- 旧进程未关闭时新进程启动报 `listen tcp :8080 bind`
- Windows 清理：
  ```powershell
  Get-NetTCPConnection -LocalPort 8080 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  ```

### 坑5：edit 工具精确匹配
- `edit` 工具要求 oldText 与文件内容完全匹配（含空白/换行）
- 遇到匹配失败时改用 `write` 工具整文件覆写

---

## Cherry Studio 配置模板

### OpenAI 提供商（推荐优先用）
- 提供商类型：OpenAI 兼容
- Base URL：http://127.0.0.1:8080/v1
- API Key：mytoken123（改成你实际的 bearer_token）
- 模型：gpt-5.4

### Anthropic 提供商
- 提供商类型：Anthropic
- Base URL：http://127.0.0.1:8080
- API Key：mytoken123（改成你实际的 bearer_token）
- 模型：claude-opus-4-6

> 注意：Base URL 不要带 /v1（Anthropic 提供商会自动拼接 /v1/messages）

---

## 验收命令（可直接复制执行）

```powershell
# 1. 清理端口
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 2. 启动服务
cd G:\AI\monica\monica-proxy-master
go run main.go
# 或用备份二进制：
# .\monica-proxy.exe

# 3. 测 OpenAI
curl.exe -i http://127.0.0.1:8080/v1/models -H "Authorization: Bearer mytoken123"

# 4. 测 Anthropic（非流式）
curl.exe -i http://127.0.0.1:8080/v1/messages `
  -H "x-api-key: mytoken123" `
  -H "Content-Type: application/json" `
  -d '{"model":"gpt-5.4","max_tokens":64,"messages":[{"role":"user","content":"你好"}],"stream":false}'
```

---

## 文件清单（本次新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| internal/apiserver/responses.go | 新增 | OpenAI Responses API 适配 |
| internal/apiserver/anthropic_compat.go | 新增 | Anthropic Messages API 适配 |
| internal/apiserver/router.go | 修改 | 注册 /v1/responses 和 /v1/messages |
| internal/middleware/auth.go | 修改 | 兼容 x-api-key / Authorization |
| deploy/ubuntu/start.sh | 新增 | Ubuntu 启动脚本 |
| deploy/ubuntu/monica-proxy.service | 新增 | systemd 服务配置 |
| deploy/ubuntu/DUAL_API_DEPLOY.md | 新增 | Ubuntu 部署文档 |
