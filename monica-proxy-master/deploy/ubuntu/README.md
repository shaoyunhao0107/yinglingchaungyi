# Monica Proxy - Ubuntu 部署指南

## 文件说明

| 文件 | 用途 |
|------|------|
| `install.sh` | 一键安装（编译 + systemd 注册 + 开机自启） |
| `update.sh` | 更新/重新编译（新增模型后使用） |
| `cookie-refresh.sh` | 快速更新 Cookie 并重启服务 |

---

## 快速安装

### 前提条件

- Ubuntu 20.04 / 22.04 / 24.04
- amd64 或 arm64 架构
- sudo 权限
- 已有 Monica 账号 Cookie（从浏览器抓取）

### 步骤

```bash
# 1. 进入部署目录
cd /path/to/monica-proxy-master/deploy/ubuntu

# 2. 添加执行权限
chmod +x install.sh update.sh cookie-refresh.sh

# 3. 执行安装
bash install.sh
```

安装完成后，编辑配置文件：

```bash
sudo nano /opt/monica-proxy/config.yaml
```

填入 Cookie（必填）：

```yaml
monica:
  cookie: "<从浏览器复制的完整 Cookie>"

security:
  bearer_token: "mytoken123"   # 自定义，对接客户端要一致
```

启动服务：

```bash
sudo systemctl start monica-proxy
```

验证：

```bash
curl -s http://localhost:8080/v1/models -H 'Authorization: Bearer mytoken123'
```

---

## 服务管理

```bash
# 启动
sudo systemctl start monica-proxy

# 停止
sudo systemctl stop monica-proxy

# 重启
sudo systemctl restart monica-proxy

# 查看状态
sudo systemctl status monica-proxy

# 实时日志
sudo journalctl -u monica-proxy -f

# 最近 50 行日志
sudo journalctl -u monica-proxy -n 50 --no-pager
```

---

## Cookie 失效处理

症状：API 返回 401 或 `认证失败`

```bash
# 方式一：脚本一键更新
bash cookie-refresh.sh "session_id=eyJ...; _ga=GA1..."

# 方式二：手动编辑
sudo nano /opt/monica-proxy/config.yaml
# 修改 monica.cookie 字段
sudo systemctl restart monica-proxy
```

### 如何获取 Cookie

1. 浏览器打开 https://monica.im 并登录
2. F12 → Network 标签
3. 在 Monica 页面随便发一条消息
4. 找到发往 `api.monica.im` 的请求
5. Request Headers → 找 `cookie:` 字段 → 复制完整值

---

## 新增模型（Monica 官网出新模型后）

### 第一步：抓包拿到 bot_uid

1. 浏览器打开 Monica 官网，切换到新模型发一条消息
2. F12 → Network → 找 `preview_chat` 请求
3. Payload（请求体）中找 `bot_uid` 字段，复制其值

### 第二步：修改映射表

编辑源码文件：

```bash
nano /path/to/monica-proxy-master/internal/types/monica.go
```

在 `modelToBotMap` 中追加一行：

```go
var modelToBotMap = map[string]string{
    // ... 已有条目 ...

    // 新增模型（左边=外部调用名，右边=抓包拿到的 bot_uid）
    "gpt-5": "gpt_5",
}
```

### 第三步：重新编译并部署

```bash
bash /path/to/monica-proxy-master/deploy/ubuntu/update.sh
```

脚本会自动：停服务 → 编译 → 替换二进制 → 启动 → 验证

### 第四步：验证新模型

```bash
curl -s http://localhost:8080/v1/models \
  -H 'Authorization: Bearer mytoken123' | grep '新模型名'
```

---

## 环境变量方式配置（可选）

如果不想把 Cookie 写进 `config.yaml`，可以用环境变量覆盖：

创建 `/opt/monica-proxy/.env`：

```bash
sudo tee /opt/monica-proxy/.env > /dev/null <<EOF
MONICA_COOKIE=session_id=eyJ...你的完整Cookie...
BEARER_TOKEN=mytoken123
EOF
```

systemd 服务已配置 `EnvironmentFile=-/opt/monica-proxy/.env`，重启后自动加载。

```bash
sudo systemctl restart monica-proxy
```

---

## 目录结构（安装后）

```
/opt/monica-proxy/
├── monica          ← 编译好的二进制
├── config.yaml     ← 主配置文件
├── config.yaml.bak ← 自动备份
└── .env            ← 环境变量（可选）

/etc/systemd/system/
└── monica-proxy.service  ← systemd 服务文件
```

---

## 常见问题

**Q: 编译时报 `go: command not found`**

```bash
export PATH=$PATH:/usr/local/go/bin
# 或重新登录 SSH 让 .bashrc 生效
```

**Q: 端口 8080 被占用**

```bash
# 修改 config.yaml 中 server.port 为其他端口，如 8088
# 或查看占用
sudo lsof -i :8080
```

**Q: 服务启动失败**

```bash
sudo journalctl -u monica-proxy -n 50 --no-pager
# 常见原因：Cookie 格式错误、config.yaml 缩进有误
```

**Q: ARM 服务器（如树莓派、Oracle Free Tier）**

脚本自动检测 `aarch64` 架构并编译 arm64 版本，无需额外配置。
 