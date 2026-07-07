#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

detect_os() {
  case "$(uname -s 2>/dev/null || echo unknown)" in
    Linux*) echo "linux" ;;
    Darwin*) echo "macos" ;;
    CYGWIN*|MINGW*|MSYS*) echo "windows" ;;
    *) echo "unknown" ;;
  esac
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  elif command -v py >/dev/null 2>&1; then
    echo "py -3"
  else
    echo "Python 3 is required but was not found." >&2
    exit 1
  fi
}

activate_venv() {
  if [[ -f ".venv/bin/activate" ]]; then
    # Linux/macOS/WSL
    source .venv/bin/activate
  elif [[ -f ".venv/Scripts/activate" ]]; then
    # Git Bash/MSYS/Cygwin on Windows
    source .venv/Scripts/activate
  else
    echo "Could not find virtualenv activation script in .venv." >&2
    exit 1
  fi
}

python_has() {
  python - "$1" <<'PY' >/dev/null 2>&1
import importlib.util
import sys

sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)
PY
}

has_sudo() {
  command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1
}

install_linux_system_webview_packages() {
  if [[ "${REVERSE_ENGINEERING_SKIP_SYSTEM_PACKAGES:-0}" == "1" ]]; then
    return
  fi

  if ! has_sudo; then
    cat <<'MSG'
Linux desktop note: no passwordless sudo is available, so run.sh will use the pip Qt backend.
If pywebview still cannot open a window, install your distro's WebKit/GTK packages manually.
Ubuntu/Debian example:
  sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0
MSG
    return
  fi

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3-gobject gtk3 webkit2gtk4.0 || true
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm python-gobject gtk3 webkit2gtk || true
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y python3-gobject gtk3 webkit2gtk3 || true
  fi
}

ensure_desktop_packages() {
  local os_name="$1"

  echo "Checking desktop dependencies for $os_name..."

  case "$os_name" in
    linux)
      # pywebview requires either GTK or Qt on Linux. Qt is the most portable
      # pip-managed option, while GTK may still need distro packages.
      install_linux_system_webview_packages
      if ! python_has qtpy; then
        python -m pip install "pywebview[qt]"
      fi
      ;;
    macos)
      # These are enough for pywebview's Cocoa backend with non-system Python.
      python -m pip install \
        pyobjc-core \
        pyobjc-framework-Cocoa \
        pyobjc-framework-Quartz \
        pyobjc-framework-WebKit \
        pyobjc-framework-security
      ;;
    windows)
      # pywebview uses Windows native backends. WebView2 Runtime is normally
      # present on modern Windows; if not, install it from Microsoft.
      python -m pip install pywebview
      cat <<'MSG'
Windows desktop note: if the window fails with a WebView2 error, install Microsoft Edge WebView2 Runtime:
  https://developer.microsoft.com/microsoft-edge/webview2/
MSG
      ;;
    *)
      python -m pip install pywebview
      ;;
  esac
}

usage() {
  cat <<'MSG'
ADB Device Manager runner

Usage:
  ./run.sh [web|desktop|test|build|install]

Examples:
  ./run.sh
  ./run.sh web
  ./run.sh desktop
  ./run.sh test
  ./run.sh build

Defaults to desktop mode.
MSG
}

install_packages() {
  local requirements_file="$1"

  echo "Installing packages from $requirements_file..."
  python -m pip install --upgrade pip
  python -m pip install -r "$requirements_file"
}

PYTHON_BIN="$(find_python)"
OS_NAME="$(detect_os)"

if [[ ! -d ".venv" ]]; then
  echo "Creating virtual environment..."
  # shellcheck disable=SC2086
  $PYTHON_BIN -m venv .venv
fi

activate_venv

choice="${1:-desktop}"

case "$choice" in
  -h|--help|help)
    usage
    ;;
  1|web|WEB|api|API)
    install_packages requirements.txt
    echo "Starting web panel..."
    exec python app.py
    ;;
  2|desktop|DESKTOP)
    install_packages requirements-desktop.txt
    ensure_desktop_packages "$OS_NAME"
    echo "Starting desktop panel..."
    exec python desktop.py
    ;;
  test|TEST)
    install_packages requirements.txt
    echo "Running Python tests..."
    exec python -m pytest -q
    ;;
  build|BUILD)
    install_packages requirements-desktop.txt
    ensure_desktop_packages "$OS_NAME"
    case "$OS_NAME" in
      macos) spec="build/macos.spec" ;;
      linux) spec="build/linux.spec" ;;
      *)
        echo "Build mode is only configured here for macOS/Linux. Use scripts/run.ps1 on Windows." >&2
        exit 1
        ;;
    esac
    echo "Building desktop package with $spec..."
    exec python -m PyInstaller "$spec" --noconfirm
    ;;
  install|INSTALL)
    install_packages requirements-desktop.txt
    ensure_desktop_packages "$OS_NAME"
    ;;
  *)
    echo "Unknown choice: $choice" >&2
    usage >&2
    exit 1
    ;;
esac
