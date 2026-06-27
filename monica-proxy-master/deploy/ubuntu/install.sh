#!/bin/bash
# Monica Proxy - Ubuntu 一键安装脚本
# 用法: bash install.sh
# 支持: Ubuntu 20.04 / 22.04 / 24.04 (amd64 / arm64)

set -e

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${COLOR_GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${COLOR_YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${COLOR_RED}[ERR ]${NC} $1"; exit 1; }

# ---------- 检测架构 ----------
ARCH=$(uname -m)
case $ARCH in
  x86_64)  GOARCH=amd64 ;;
  aarch64) GOARCH=arm64 ;;
  *) err "不支持的架构: $ARCH" ;;
esac
log "系统架构: $ARCH ($GOARCH)"

# ---------- 安装目录 ----------
INSTALL_DIR="${INSTALL_DIR:-/opt/monica-proxy}"
log "安装目录: $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"

# ---------- 方式一：从源码编译（推荐，确保最新模型映射）----------
build_from_source() {
  log "检查 Go 环境..."
  if ! command -v go &>/dev/null; then
    log "Go 未安装，正在安装 Go 1.24..."
    wget -q https://go.dev/dl/go1.24.3.linux-${GOARCH}.tar.gz -O /tmp/go.tar.gz
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf /tmp/go.tar.gz
    echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
    export PATH=$PATH:/usr/local/go/bin
    log "Go 安装完成: $(go version)"
  else
    log "Go 已安装: $(go version)"
  fi

  # 确定源码目录（兼容脚本放在 deploy/ubuntu/ 或项目根的情况）
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SRC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
  if [ ! -f "$SRC_DIR/go.mod" ]; then
    SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  fi
  if [ ! -f "$SRC_DIR/go.mod" ]; then
    SRC_DIR="$SCRIPT_DIR"
  fi
  log "源码目录: $SRC_DIR"

  log "编译中..."
  cd "$SRC_DIR"
  CGO_ENABLED=0 GOOS=linux GOARCH=$GOARCH go build -ldflags "-s -w" -o /tmp/monica-proxy-bin .
  sudo cp /tmp/monica-proxy-bin "$INSTALL_DIR/monica"
  sudo chmod +x "$INSTALL_DIR/monica"
  log "编译完成"
}

# ---------- 复制配置文件 ----------
setup_config() {
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SRC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
  if [ ! -f "$SRC_DIR/config.example.yaml" ]; then
    SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  fi
  if [ ! -f "$SRC_DIR/config.example.yaml" ]; then
    SRC_DIR="$SCRIPT_DIR"
  fi

  if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    if [ -f "$SRC_DIR/config.example.yaml" ]; then
      sudo cp "$SRC_DIR/config.example.yaml" "$INSTALL_DIR/config.yaml"
      log "已复制 config.example.yaml → $INSTALL_DIR/config.yaml"
    else
      sudo tee "$INSTALL_DIR/config.yaml" > /dev/null <<'CONFEOF'
server:
  host: "0.0.0.0"
  port: 8080
  read_timeout: "30s"
  write_timeout: "30s"
  idle_timeout: "60s"

monica:
  cookie: "<在这里填入你的 Monica Cookie>"   # ← 必填

security:
  bearer_token: "mytoken123"
CONFEOF
      log "已生成默认 config.yaml（未找到 config.example.yaml）"
    fi
    warn "请编辑 $INSTALL_DIR/config.yaml 填入 Monica Cookie"
  else
    log "config.yaml 已存在，跳过覆盖"
  fi
}

# ---------- 创建 systemd 服务 ----------
setup_systemd() {
  log "配置 systemd 服务..."
  sudo tee /etc/systemd/system/monica-proxy.service > /dev/null <<EOF
[Unit]
Description=Monica Proxy - OpenAI Compatible API
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=nobody
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/monica
Restart=on-failure
RestartSec=5s
EnvironmentFile=-$INSTALL_DIR/.env
StandardOutput=journal
StandardError=journal
SyslogIdentifier=monica-proxy

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable monica-proxy
  log "systemd 服务已创建并设置为开机自启"
}

# ---------- 主流程 ----------
build_from_source
setup_config
setup_systemd

echo ""
echo -e "${COLOR_GREEN}==============================${NC}"
echo -e "${COLOR_GREEN} Monica Proxy 安装完成！${NC}"
echo -e "${COLOR_GREEN}==============================${NC}"
echo ""
echo "下一步："
echo "  1. 编辑配置文件，填入 Monica Cookie："
echo "     sudo nano $INSTALL_DIR/config.yaml"
echo ""
echo "  2. 启动服务："
echo "     sudo systemctl start monica-proxy"
echo ""
echo "  3. 验证："
echo "     curl -s http://localhost:8080/v1/models -H 'Authorization: Bearer mytoken123'"
echo ""
ld_from_source
setup_config
setup_systemd

echo ""
echo -e "${COLOR_GREEN}==============================${NC}"
echo -e "${COLOR_GREEN} Monica Proxy 安装完成！${NC}"
echo -e "${COLOR_GREEN}==============================${NC}"
echo ""
echo "下一步："
echo "  1. 编辑配置文件，填入 Monica Cookie："
echo "     sudo nano $INSTALL_DIR/config.yaml"
echo ""
echo "  2. 启动服务："
echo "     sudo systemctl start monica-proxy"
echo ""
echo "  3. 验证："
echo "     curl -s http://localhost:8080/v1/models -H 'Authorization: Bearer mytoken123'"
echo ""
