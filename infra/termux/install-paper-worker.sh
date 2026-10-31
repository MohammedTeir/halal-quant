#!/data/data/com.termux/files/usr/bin/bash
set -eu
: "${PREFIX:?Run from the main Termux shell}"
if [ -f /etc/debian_version ]; then
  echo 'Run from the main Termux shell, not Debian.'
  exit 1
fi
run_id=${1:?Usage: bash install-paper-worker.sh RUN_ID}
if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9_.:-]*$ ]] || [ "${#run_id}" -gt 200 ]; then
  echo 'Use the exact reviewed run ID (letters, digits, dot, colon, underscore, dash).'
  exit 1
fi
for program in sv pgrep proot-distro; do command -v "$program" >/dev/null; done
service="$PREFIX/var/service/halal-paper"
if [ -d "$service" ]; then
  if [ "$(cat "$service/run-id")" != "$run_id" ]; then
    echo 'The installed service belongs to another run. Stop it and review its configuration first.'
    exit 1
  fi
  echo 'Service already installed for this run. Use its full service path with sv.'
  exit 0
fi
if pgrep -f '^([^[:space:]]*/)?python([0-9]+([.][0-9]+)*)?[[:space:]]+-m[[:space:]]+services[.]paper[.]worker([[:space:]]|$)' >/dev/null; then
  echo 'Stop the unmanaged paper worker before installing supervision.'
  exit 1
fi
umask 077
mkdir -p "$PREFIX/var/service" "$PREFIX/var/log/sv/halal-paper" "$PREFIX/var/tmp"
workdir=$(mktemp -d "$PREFIX/var/tmp/halal-paper.XXXXXXXX")
trap 'rm -rf "$workdir"' EXIT
mkdir -p "$workdir/log" "$workdir/control"
touch "$workdir/down"
printf '%s\n' "$run_id" > "$workdir/run-id"
cat > "$workdir/run" <<RUN
#!$PREFIX/bin/sh
exec 2>&1
exec $PREFIX/bin/proot-distro login debian -- bash -lc 'cd /root/halal-quant && exec .venv/bin/python -m services.paper.worker --run-id $run_id'
RUN
cat > "$workdir/log/run" <<LOG
#!$PREFIX/bin/sh
exec $PREFIX/bin/svlogd -tt $PREFIX/var/log/sv/halal-paper
LOG
cat > "$workdir/control/t" <<'CONTROL'
#!/data/data/com.termux/files/usr/bin/bash
# Forward supervisor termination through proot without fixed process IDs.
service="$PREFIX/var/service/halal-paper"
parent=$(sv status "$service" | sed -n 's/^[^(]*(pid \([0-9][0-9]*\)).*/\1/p')
[ -n "$parent" ] || exit 1
forwarded=false
for child in $(pgrep -P "$parent" -f '^[^ ]*python[^ ]* -m services[.]paper[.]worker([[:space:]]|$)' || true); do
  kill -TERM "$child" 2>/dev/null && forwarded=true
 done
[ "$forwarded" = true ]
CONTROL
printf 's1048576\nn3\n' > "$PREFIX/var/log/sv/halal-paper/config"
chmod 700 "$workdir/run" "$workdir/log/run" "$workdir/control/t"
mv "$workdir" "$service"
trap - EXIT
echo 'Installed disabled. Complete the private configuration and worker --check before enabling.'
echo 'This is a separate service; the Telegram notification worker is unchanged.'
echo 'Android can terminate Termux; runit cannot guarantee unattended Android uptime.'
