#!/usr/bin/env sh
set -eu

ACTION="web"
USE_SYSTEM=0
DESKTOP_DEPS=0

usage() {
  cat <<'EOF'
ADB Device Manager runner

Usage:
  sh scripts/run.sh [web|desktop|test|build|install] [--system-python] [--desktop-deps]

Examples:
  sh scripts/run.sh
  sh scripts/run.sh desktop --desktop-deps
  sh scripts/run.sh test
  sh scripts/run.sh build --desktop-deps

Defaults to a managed .venv. Use --system-python to run with active/system Python.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    web|desktop|test|build|install) ACTION="$1" ;;
    --system-python) USE_SYSTEM=1 ;;
    --desktop-deps) DESKTOP_DEPS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENV_DIR="$REPO_ROOT/.venv"
PY="$VENV_DIR/bin/python"

find_python() {
  if command -v python3 >/dev/null 2>&1; then echo python3; return; fi
  if command -v python >/dev/null 2>&1; then echo python; return; fi
  echo "Python 3 was not found." >&2
  exit 1
}

ensure_venv() {
  if [ -x "$PY" ]; then return; fi
  SYS_PY=$(find_python)
  echo "Creating .venv..." >&2
  "$SYS_PY" -m venv "$VENV_DIR"
}

python_cmd() {
  if [ "$USE_SYSTEM" -eq 1 ]; then
    find_python
  else
    ensure_venv
    echo "$PY"
  fi
}

install_deps() {
  PYTHON=$(python_cmd)
  "$PYTHON" -m pip install --upgrade pip
  if [ "$DESKTOP_DEPS" -eq 1 ]; then
    "$PYTHON" -m pip install -r requirements-desktop.txt
  else
    "$PYTHON" -m pip install -r requirements.txt
  fi
}

cd "$REPO_ROOT"

case "$ACTION" in
  install)
    install_deps
    ;;
  web)
    install_deps
    "$(python_cmd)" app.py
    ;;
  desktop)
    DESKTOP_DEPS=1
    install_deps
    "$(python_cmd)" desktop.py
    ;;
  test)
    install_deps
    "$(python_cmd)" -m pytest -q
    ;;
  build)
    DESKTOP_DEPS=1
    install_deps
    OS_NAME=$(uname -s)
    case "$OS_NAME" in
      Darwin) SPEC="build/macos.spec" ;;
      Linux) SPEC="build/linux.spec" ;;
      *) echo "Use scripts/run.ps1 -Action build-windows on Windows." >&2; exit 1 ;;
    esac
    "$(python_cmd)" -m PyInstaller "$SPEC" --noconfirm
    ;;
esac
