#!/data/data/com.termux/files/usr/bin/bash
set -eu
: "${PREFIX:?Run this from the main Termux shell, not inside Debian}"
command -v proot-distro >/dev/null
command -v pgrep >/dev/null || { echo "Install procps in Termux first."; exit 1; }
command -v sv >/dev/null || { echo 'Install termux-services and reopen the Termux shell first.'; exit 1; }
if [ -f /etc/debian_version ]; then
  echo 'Run from the main Termux shell, not inside Debian.'
  exit 1
fi
service="$PREFIX/var/service/halal-quant"
if [ -d "$service" ]; then
  echo 'The managed service already exists. Use sv up halal-quant or sv restart halal-quant.'
  exit 0
fi
# Match the Python executable at the start of argv, not a tmux launcher
# whose arguments contain the original worker command.
if pgrep -f '^([^[:space:]]*/)?python([0-9]+([.][0-9]+)*)?[[:space:]]+-m[[:space:]]+services[.]notifications[.]worker([[:space:]]|$)' >/dev/null; then
  echo 'Stop the old worker with Ctrl+C before installing the supervised worker.'
  exit 1
fi
umask 077
mkdir -p "$PREFIX/var/service" "$PREFIX/var/log/sv/halal-quant" "$PREFIX/var/tmp"
workdir=$(mktemp -d "$PREFIX/var/tmp/halal-worker.XXXXXXXX")
trap 'rm -rf "$workdir"' EXIT
mkdir -p "$workdir/log"
touch "$workdir/down"
cat > "$workdir/run" <<EOF
#!$PREFIX/bin/sh
exec 2>&1
exec $PREFIX/bin/proot-distro login debian -- bash -lc 'cd /root/halal-quant && exec .venv/bin/python -m services.notifications.worker --expected-bot halalquant_bot'
EOF
cat > "$workdir/log/run" <<EOF
#!$PREFIX/bin/sh
exec $PREFIX/bin/svlogd -tt $PREFIX/var/log/sv/halal-quant
EOF
printf 's1048576\nn3\n' > "$PREFIX/var/log/sv/halal-quant/config"
chmod 700 "$workdir/run" "$workdir/log/run"
mv "$workdir" "$service"
trap - EXIT
echo 'Installed disabled. Run: sv-enable halal-quant'
echo 'runit will restart an exited worker while Termux remains alive; Android can still terminate the entire app.'
