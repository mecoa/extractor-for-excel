#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

VENV_LIB="$DIR/.venv/lib"

# Ensure dependencies
if [ ! -d "$DIR/.venv" ]; then
    echo ">>> 首次运行，安装依赖..."
    uv sync
fi

# Fix missing libEGL (common on WSL)
if ! ldconfig -p 2>/dev/null | grep -q "libEGL.so.1"; then
    if [ ! -f "$VENV_LIB/libEGL.so.1" ]; then
        echo ">>> 检测到系统缺少 libEGL.so.1，尝试自动修复..."
        mkdir -p "$VENV_LIB"
        TMPD=$(mktemp -d)
        wget -q -O "$TMPD/libegl.deb" \
            "http://ftp.debian.org/debian/pool/main/libg/libglvnd/libegl1_1.7.0-1+b2_amd64.deb" && {
            dpkg -x "$TMPD/libegl.deb" "$TMPD/ext"
            cp "$TMPD/ext/usr/lib/x86_64-linux-gnu/libEGL.so"* "$VENV_LIB/"
            echo ">>> 已修复"
        } || {
            echo ">>> 自动修复失败，手动执行: sudo apt-get install -y libegl1"
        }
        rm -rf "$TMPD"
    fi
fi

export LD_LIBRARY_PATH="$VENV_LIB:$LD_LIBRARY_PATH"

exec uv run python main.py "$@"
