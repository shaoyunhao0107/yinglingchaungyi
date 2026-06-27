# Monica Proxy 安装与使用指南

> 适用于 Windows x64 系统（其他系统需自行从源码编译）

---

## 一、快速安装

### 1. 解压发布包

将 `monica-proxy-release-YYYYMMDD.zip` 解压到任意目录，例如：

```
C:\monica-proxy\
├── monica-proxy.exe
└── config.example.yaml
```

### 2. 创建配置文件

将 `config.example.yaml` 复制并重命名为 `config.yaml`：

```bash
copy config.example.yaml config.yaml
```

### 3. 编辑 config.yaml

用文本编辑器打开 `config.yaml`，填写以下必填项：

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  read_timeout: "30s"
  write_timeout: "30s"
  idle_timeout: "60s"

monica:
  cookie: "<在这里填入你的 Monica Cookie>"   # ← 必填

security:
  bearer_token: "mytoken123"               # ← 可自定义，客户端需用此 Token
  tls_skip_verify: true
  rate_limit_enabled: false
  rate_limit_rps: 0
  request_timeout: "30s"

http_client:
  timeout: "3m"
  max_idle_conns: 100
  max_idle_conns_per_host: 10
  max_conns_per_host: 50
  retry_count: 3
  retry_wait_time: "1s"
  retry_max_wait_time: "10s"

logging:
  level: "info"
  format: "console"
  output: "stdout"
  enable_request_log: true
  mask_sensitive: true
```

---

## 二、获取 Monica Cookie

1. 用浏览器打开 [https://monica.im](https://monica.im) 并登录
2. 按 `F12` 打开开发者工具 → 切换到 **Network（网络）** 标签
3. 随意发送一条对话消息
4. 找到任意一条发往 `monica.im` 的请求，点击它
5. 在 **Request Headers（请求头）** 中找到 `cookie:` 字段
6. 复制完整的 cookie 值（很长，包含 `session_id=...` 等多段）
7. 粘贴到 `config.yaml` 的 `monica.cookie` 字段（保留引号）

> ⚠️ Cookie 有有效期，如果服务返回认证错误，需重新获取并更新。

---

## 三、启动服务

### 方式 A：直接运行（前台，可看日志）

```powershell
cd C:\monica-proxy
.\monica-proxy.exe -port8080
```

### 方式 B：后台静默运行

```powershell
Start-Process -FilePath '.\monica-proxy.exe' -ArgumentList '-port8080' -WindowStyle Hidden
```

### 方式 C：开机自启（Task Scheduler）

1. 打开「任务计划程序」→「创建基本任务」
2. 触发器选「计算机启动时」
3. 操作选「启动程序」
4. 程序：`C:\monica-proxy\monica-proxy.exe`
5. 参数：`-port8080`
6. 起始目录：`C:\monica-proxy`

---

## 四、在 Cherry Studio 中配置

1. 打开 Cherry Studio → 设置 → 模型服务
2. 新增服务商，选择 **OpenAI 兼容**
3. 填写：
   - **Base URL**：`http://localhost:8080/v1`
   - **API Key**：`mytoken123`（与 `config.yaml` 中 `bearer_token` 一致）
4. 添加模型（手动输入模型名）：
   - `gpt-4o`
   - `gpt-5.4`
   - `claude-sonnet-4-6`
   - `claude-sonnet-4-5`
5. 点击测试连接，绿色即成功

---

## 五、验证服务是否正常

```powershell
curl.exe -s -X POST http://localhost:8080/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer mytoken123" `
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"你好"}],"max_tokens":32,"stream":false}'
```

正常响应示例：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "你好！有什么可以帮助你的吗？"
    },
    "finish_reason": "stop"
  }]
}
```

---

## 六、常见问题

### Q: 服务启动失败，提示 `yaml: could not find expected ':'`

A: `config.yaml` 格式有误。检查所有 `key: value` 之间是否有空格，例如 `port: 8080`（不能写成 `port:8080`）。

### Q: 返回「月度查询次数已用尽」

A: Monica 账号当月 1600 次高级查询已耗尽，每天仍有 100 次限速额度，下月 1 日自动恢复。可换新账号 Cookie 继续使用。

### Q: 返回 401 Unauthorized

A: 请求头 `Authorization: Bearer <token>` 与 `config.yaml` 中 `bearer_token` 不一致。

### Q: 端口被占用

```powershell
# 查看占用 8080 的进程
Get-NetTCPConnection -LocalPort 8080 -State Listen
# 强制结束
Stop-Process -Id <PID> -Force
```

### Q: Cookie 失效后如何更新

重新从浏览器获取 Cookie，直接编辑 `config.yaml` 替换 `monica.cookie` 的值，然后重启服务即可。

---

## 七、注意事项

- Monica 仅供**个人提升效率**使用，**禁止商业用途或自动化批量调用**
- Cookie 含登录凭证，**不要分享给他人或上传到公开仓库**
- 服务默认监听所有网卡（`0.0.0.0`），局域网内其他设备也可访问，注意安全

---

*最后更新：2026-03-24*
