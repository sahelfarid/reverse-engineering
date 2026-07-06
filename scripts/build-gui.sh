#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNNER="$SCRIPT_DIR/run.sh"

SYSTEM_FLAG=""

choose_mode() {
  echo
  echo "Python mode:"
  echo "  1) Managed .venv (default)"
  echo "  2) Active/system Python"
  printf "Choose [1-2]: "
  read ans
  case "$ans" in
    2) SYSTEM_FLAG="--system-python" ;;
    *) SYSTEM_FLAG="" ;;
  esac
}

run_action() {
  ACTION="$1"
  DESKTOP="${2:-}"
  if [ "$DESKTOP" = "desktop" ]; then
    sh "$RUNNER" "$ACTION" $SYSTEM_FLAG --desktop-deps
  else
    sh "$RUNNER" "$ACTION" $SYSTEM_FLAG
  fi
}

choose_mode

while :; do
  echo
  echo "ADB Device Manager build menu"
  echo "  1) Install deps"
  echo "  2) Run web app"
  echo "  3) Run desktop app"
  echo "  4) Run tests"
  echo "  5) Build desktop package for this OS"
  echo "  6) Change Python mode"
  echo "  0) Exit"
  printf "Choose [0-6]: "
  read choice
  case "$choice" in
    1) run_action install desktop ;;
    2) run_action web ;;
    3) run_action desktop desktop ;;
    4) run_action test ;;
    5) run_action build desktop ;;
    6) choose_mode ;;
    0) exit 0 ;;
    *) echo "Unknown choice." ;;
  esac
done
