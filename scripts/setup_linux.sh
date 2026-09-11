#!/usr/bin/env bash
# 抖音好友 AI 机器人 —— Linux 一键环境准备脚本
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "!! 请以 root 身份运行此部署脚本" >&2
  exit 1
fi

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
echo "==> 项目目录：$APP_DIR"
if [ ! -r /etc/os-release ]; then
  echo "!! 无法识别系统：缺少 /etc/os-release" >&2; exit 1
fi
. /etc/os-release
if [ "${ID:-}" != "alinux" ] || [ "${VERSION_ID:-}" != "3" ]; then
  echo "!! 当前系统环境不受此脚本支持：${PRETTY_NAME:-未知}" >&2; exit 1
fi
if ! command -v dnf >/dev/null 2>&1; then
  echo "!! 缺少 dnf，无法安装系统依赖" >&2; exit 1
fi

# 0) 使用 Python 3.11。
if ! command -v python3.11 >/dev/null 2>&1; then
  echo "==> 安装 Python 3.11……"
  dnf install -y python3.11 python3.11-pip
fi
PICK="$(command -v python3.11)"
echo "==> 使用 Python: $PICK ($("$PICK" -V 2>&1))"

# 1) Xvfb
if ! command -v Xvfb >/dev/null; then
  echo "==> 安装 Xvfb……"
  dnf install -y xorg-x11-server-Xvfb
fi
echo "==> Xvfb 就绪"

# 2) 虚拟环境 + 依赖（pip 走清华镜像）
PIP_INDEX="-i https://pypi.tuna.tsinghua.edu.cn/simple"
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "==> 复用现有 .venv"
else
  echo "==> 创建虚拟环境……"
  if [ -e .venv ]; then
    backup_dir=".venv.backup-$(date +%Y%m%d-%H%M%S)"
    mv .venv "$backup_dir"
    echo "==> 已备份旧虚拟环境到 $backup_dir"
  fi
  "$PICK" -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip $PIP_INDEX
.venv/bin/pip install -q -r requirements.txt $PIP_INDEX
echo "==> 依赖安装完成"

# 3) 浏览器：引擎固定 firefox（chromium/edge 走 CDP 协议，会被抖音前端检测，
#    点不开会话，已实测弃用）。playwright install 幂等：对应 build 已在就跳过下载。
echo "==> 确保 Firefox 就绪……"
PLAYWRIGHT_BROWSERS_PATH="$APP_DIR/ms-playwright" .venv/bin/python -m playwright install firefox

# 4) Firefox 必须能真正运行（系统太老 / glibc 不够会在这里暴露）
FF_BIN="$(ls ms-playwright/firefox-*/firefox/firefox 2>/dev/null | head -1 || true)"
if [ -z "$FF_BIN" ] || ! "$FF_BIN" --version >/dev/null 2>&1; then
  echo "!! Firefox 无法在此系统运行（多半系统太老、glibc 不够新）"
  echo "   实际报错：$("$FF_BIN" --version 2>&1 | head -1)"
  echo "   请确认系统依赖已正确安装"
  exit 1
fi
echo "✅ Firefox 可运行: $("$FF_BIN" --version 2>/dev/null)"

# 5) 浏览器共享库检查
MISSING="$(ldd "$FF_BIN" 2>/dev/null | grep 'not found' | awk '{print $1}' | sort -u | tr '\n' ' ' || true)"
if [ -n "$MISSING" ]; then
  echo "==> 缺少浏览器依赖库：$MISSING，尝试补装……"
  dnf install -y alsa-lib atk at-spi2-atk cairo cups-libs dbus-glib fontconfig freetype glib2 gtk3 libdrm libX11 libXcomposite libXdamage libXext libXfixes libXrandr libXrender libXtst libxcb libxkbcommon mesa-libgbm nss pango xorg-x11-server-Xvfb
  MISSING2="$(ldd "$FF_BIN" 2>/dev/null | grep 'not found' | awk '{print $1}' | sort -u | tr '\n' ' ' || true)"
  if [ -n "$MISSING2" ]; then
    echo "!! 仍缺库：$MISSING2（请手动安装后重跑本脚本）"
    exit 1
  fi
fi

mkdir -p logs/screenshots state

echo
echo "✅ 环境就绪。接下来："
echo "  1) 只跑一次：.venv/bin/python src/main.py --check-login"
echo "  2) 通过后配置宝塔面板；面板用 www 用户则先 chown -R www:www logs state"
