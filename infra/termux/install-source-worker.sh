#!/data/data/com.termux/files/usr/bin/bash
set -eu
: "${PREFIX:?Run from the main Termux shell}"
if [ -f /etc/debian_version ]; then
  echo 'Run from the main Termux shell, not Debian.'
  exit 1
fi
account_file="/root/halal-quant/data/paper-setup/account.json"
for program in sv pgrep proot-distro; do command -v "$program" >/dev/null; done
service="$PREFIX/var/service/halal-sources"
if [ -d "$service" ]; then
  if [ "$(cat "$service/account-file")" != "$account_file" ]; then
    echo 'The installed service belongs to another account file. Stop it and review its configuration first.'
    exit 1
  fi
  echo 'Service already installed for this account file. Use its full service path with sv.'
  exit 0
fi
if pgrep -f '^([^[:space:]]*/)?python([0-9]+([.][0-9]+)*)?[[:space:]]+-m[[:space:]]+services[.]paper[.]sources([[:space:]]|$)' >/dev/null; then
  echo 'Stop the unmanaged source worker before installing supervision.'
  exit 1
fi
umask 077
mkdir -p "$PREFIX/var/service" "$PREFIX/var/log/sv/halal-sources" "$PREFIX/var/tmp"
workdir=$(mktemp -d "$PREFIX/var/tmp/halal-sources.XXXXXXXX")
trap 'rm -rf "$workdir"' EXIT
mkdir -p "$workdir/log" "$workdir/control"
touch "$workdir/down"
printf '%s\n' "$account_file" > "$workdir/account-file"
cat > "$workdir/run" <<RUN
#!$PREFIX/bin/sh
exec 2>&1
exec $PREFIX/bin/proot-distro login debian -- bash -lc 'cd /root/halal-quant && exec .venv/bin/python -m services.paper.sources --account-file $account_file'
RUN
cat > "$workdir/log/run" <<LOG
#!$PREFIX/bin/sh
exec $PREFIX/bin/svlogd -tt $PREFIX/var/log/sv/halal-sources
LOG
cat > "$workdir/control/t" <<'CONTROL'
#!/data/data/com.termux/files/usr/bin/bash
# Forward supervisor termination through proot without fixed process IDs.
service="$PREFIX/var/service/halal-sources"
parent=$(sv status "$service" | sed -n 's/^[^(]*(pid \([0-9][0-9]*\)).*/\1/p')
[ -n "$parent" ] || exit 1
forwarded=false
for child in $(pgrep -P "$parent" -f '^[^ ]*python[^ ]* -m services[.]paper[.]sources([[:space:]]|$)' || true); do
  kill -TERM "$child" 2>/dev/null && forwarded=true
 done
[ "$forwarded" = true ]
CONTROL
printf 's1048576\nn3\n' > "$PREFIX/var/log/sv/halal-sources/config"
chmod 700 "$workdir/run" "$workdir/log/run" "$workdir/control/t"
mv "$workdir" "$service"
trap - EXIT
echo 'Installed disabled. Complete the private configuration and source poll before enabling.'
echo 'This is a separate service; the paper matching and Telegram notification workers are unchanged.'
echo 'Android can terminate Termux; runit cannot guarantee unattended Android uptime.'
