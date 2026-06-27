#!/bin/bash
# Monica Proxy - 更新脚本（新模型对接后重新编译部署）
# 用法: bash update.sh

set -e

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${COLOR_GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${COLOR_YELLOW}[WARN]${NC} $1"; }

INSTALL_DIR="${INSTALL_DIR:-/opt/monica-proxy}"
ARCH=$(uname -m)
case $ARCH in
  x86_64)  GOARCH=amd64 ;;
  aarch64) GOARCH=arm64 ;;
  *) echo "不支持的架构: $ARCH"; exit 1 ;;
esac

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
log "安装目录: $INSTALL_DIR"

# 停止服务
if systemctl is-active --quiet monica-proxy; then
  log "停止服务..."
  sudo systemctl stop monica-proxy
fi

# 备份旧二进制
if [ -f "$INSTALL_DIR/monica" ]; then
  sudo cp "$INSTALL_DIR/monica" "$INSTALL_DIR/monica.bak"
  log "已备份旧版本至 monica.bak"
fi

# 重新编译
log "重新编译..."
cd "$SRC_DIR"
export PATH=$PATH:/usr/local/go/bin
CGO_ENABLED=0 GOOS=linux GOARCH=$GOARCH go build -ldflags "-s -w" -o /tmp/monica-proxy-bin .
sudo cp /tmp/monica-proxy-bin "$INSTALL_DIR/monica"
sudo chmod +x "$INSTALL_DIR/monica"
log "编译完成"

# 启动服务
log "启动服务..."
sudo systemctl start monica-proxy
sleep 2

# 验证
if systemctl is-active --quiet monica-proxy; then
  log "服务启动成功"
  TOKEN=$(grep 'bearer_token' "$INSTALL_DIR/config.yaml" 2>/dev/null | awk '{print $2}' | tr -d '"' || echo 'mytoken123')
  curl -s "http://localhost:8080/v1/models" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool 2>/dev/null | head -30 || \
  curl -s "http://localhost:8080/v1/models" -H "Authorization: Bearer $TOKEN"
else
  echo "服务启动失败，查看日志:"
  sudo journalctl -u monica-proxy -n 30 --no-pager
  exit 1
fi
