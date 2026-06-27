#!/bin/bash
# Monica Proxy - Cookie 更新脚本
# 用法: bash cookie-refresh.sh "<新的完整 Cookie 字符串>"
# 示例: bash cookie-refresh.sh "session_id=eyJ...; _ga=GA1..."

set -e

COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${COLOR_GREEN}[INFO]${NC} $1"; }
err() { echo -e "${COLOR_RED}[ERR ]${NC} $1"; exit 1; }

INSTALL_DIR="${INSTALL_DIR:-/opt/monica-proxy}"
CONFIG_FILE="$INSTALL_DIR/config.yaml"

if [ -z "$1" ]; then
  err "用法: bash cookie-refresh.sh \"<完整 Cookie>\""
fi

NEW_COOKIE="$1"

if [ ! -f "$CONFIG_FILE" ]; then
  err "配置文件不存在: $CONFIG_FILE"
fi

# 备份当前配置
sudo cp "$CONFIG_FILE" "${CONFIG_FILE}.bak"
log "已备份 config.yaml → config.yaml.bak"

# 替换 cookie 行（保留缩进格式）
# 使用 Python 处理 YAML，避免 sed 转义问题
sudo python3 - <<PYEOF
import yaml, sys

with open('$CONFIG_FILE', 'r') as f:
    raw = f.read()

try:
    cfg = yaml.safe_load(raw)
except Exception as e:
    print(f'YAML 解析失败: {e}', file=sys.stderr)
    sys.exit(1)

if 'monica' not in cfg:
    cfg['monica'] = {}

cfg['monica']['cookie'] = '''$NEW_COOKIE'''

with open('$CONFIG_FILE', 'w') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

print('Cookie 已更新')
PYEOF

# 重启服务
if systemctl is-active --quiet monica-proxy; then
  log "重启服务..."
  sudo systemctl restart monica-proxy
  sleep 2
  if systemctl is-active --quiet monica-proxy; then
    log "服务重启成功，Cookie 已生效"
  else
    err "服务重启失败，查看日志: sudo journalctl -u monica-proxy -n 30"
  fi
else
  log "服务未运行，Cookie 已写入，手动启动: sudo systemctl start monica-proxy"
fi
