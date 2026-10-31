#!/data/data/com.termux/files/usr/bin/bash
# Update an already configured phone; never contains credentials.
set -eu
: "${PREFIX:?Run from the main Termux shell}"
if [ -f /etc/debian_version ]; then
  echo 'Run from the main Termux shell, not Debian.'
  exit 1
fi
export SVDIR="$PREFIX/var/service"
service="$SVDIR/halal-quant"
if [ ! -d "$service" ]; then
  echo 'Install the supervised service first; see docs/milestone-7-operational-acceptance.md.'
  exit 1
fi
termux-wake-lock
. "$PREFIX/etc/profile.d/start-services.sh"
sv down "$service"
# proot may retain TERM without forwarding it to its Python child.
wrapper_pid=$(sv status "$service" |
  sed -n 's/^[^(]*(pid \([0-9][0-9]*\)).*/\1/p')
if [ -n "$wrapper_pid" ]; then
  for worker_pid in $(pgrep -P "$wrapper_pid" -f '^[^ ]*python[^ ]* -m services[.]notifications[.]worker([[:space:]]|$)' || true); do
    kill -TERM "$worker_pid" 2>/dev/null || true
  done
fi
sv -w 30 down "$service"
proot-distro login debian -- bash -s <<'DEBIAN'
set -eu
cd /root/halal-quant
git pull --ff-only
export PATH="/opt/halal-tools-debian/bin:$HOME/.local/bin:$PATH"
uv sync --frozen --no-dev --python 3.12 --link-mode copy
.venv/bin/python -m services.notifications.worker --check --expected-bot halalquant_bot
DEBIAN
restart_after=$(date +%s)
sv -w 30 up "$service"
proot-distro login debian -- bash -s -- "$restart_after" <<'DEBIAN'
set -eu
cd /root/halal-quant
.venv/bin/python - "$1" <<'PY'
import json
import sys
import time
from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.notifications.health import view
from services.operations.worker_status import observe

engine, sessions = session_factory(get_settings().database_url)
try:
    deadline = time.monotonic() + 90
    while True:
        status = view(sessions)
        if (status['state'] == 'RECENT' and status['mode'] == 'delivery'
                and (status.get('started_at') or 0) >= int(sys.argv[1])):
            break
        if time.monotonic() >= deadline:
            print(json.dumps({'status': 'STARTUP_NOT_CONFIRMED', 'worker': status}))
            sys.exit(1)
        time.sleep(3)
    result = observe(sessions, 60)
    print(json.dumps(result))
    if result['status'] != 'PASSED':
        sys.exit(1)
finally:
    engine.dispose()
PY
DEBIAN
sv status "$service"
