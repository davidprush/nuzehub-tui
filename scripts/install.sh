#!/bin/zsh
# Install NuzeHub TUI 0.2.3 with pipx from a wheel, sdist, or this source tree.
# Usage:
#   ./scripts/install.sh
#   ./scripts/install.sh /path/to/nuzehub_tui-0.2.3-py3-none-any.whl
set -e -o pipefail
PY=${PYTHON:-python3.13}
PIPX=$(command -v pipx || true)
[ -n "$PIPX" ] || PIPX=/opt/homebrew/bin/pipx
[ -x "$PIPX" ] || { echo "pipx not found: brew install pipx"; exit 1; }
command -v "$PY" >/dev/null || { echo "$PY not found: brew install python@3.13"; exit 1; }
SRC=${1:-.}
echo "Installing NuzeHub TUI from $SRC with $PY"
"$PIPX" install --force --python "$PY" "$SRC"
BIN=$("$PIPX" environment --value PIPX_BIN_DIR)
echo "nuzehub-tui $($BIN/nuzehub-tui --version)"
echo "interpreter: $(head -1 "$(command -v nuzehub-tui)")"
echo "Open it with: nuzehub-tui          # http://127.0.0.1:8080"
echo "             nuzehub-tui --demo   # fictional desk, no network"
