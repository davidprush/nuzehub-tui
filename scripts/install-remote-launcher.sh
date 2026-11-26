#!/bin/zsh
# Write ~/.local/bin/nuzehub-remote, a launcher that runs the TUI on the
# NuzeHub server over ssh (the desk keeps listening on 127.0.0.1).
#
#   export NUZEHUB_SSH_HOST=nuzehub-server    # Host name or alias in ~/.ssh/config
#   ./scripts/install-remote-launcher.sh
#
# Default host is nuzehub-server. Nothing in this script hard-codes a
# private address or a machine-specific name.
set -e -o pipefail
HOST=${NUZEHUB_SSH_HOST:-nuzehub-server}
DEST="${NUZEHUB_REMOTE_LAUNCHER:-$HOME/.local/bin/nuzehub-remote}"
case "$HOST" in
  ''|*[!A-Za-z0-9._-]*) echo "NUZEHUB_SSH_HOST looks invalid: $HOST"; exit 1 ;;
esac
/bin/mkdir -p "${DEST:h}"
printf '%s\n' '#!/bin/zsh' "exec /usr/bin/ssh -t ${HOST} '\$HOME/.local/bin/nuzehub-tui' \"\$@\"" > "$DEST"
chmod 755 "$DEST"
echo "Wrote $DEST -> ssh -t $HOST '\$HOME/.local/bin/nuzehub-tui'"
echo "Open it with: nuzehub-remote"
