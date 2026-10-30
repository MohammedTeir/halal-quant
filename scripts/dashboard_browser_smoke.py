"""Isolated Chromium acceptance; requires Node Playwright and system Chromium.

Run with `.venv/bin/python -m scripts.dashboard_browser_smoke`.
No real email/Telegram/provider transport is used. The fixture has no service keys.
"""

import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from alembic import command
from alembic.config import Config

from apps.api.db import session_factory
from apps.api.main import create_app
from packages.config.settings import Settings, get_settings
from services.accounts.access import issue, locked
from services.notifications.models import User


def main():
    with tempfile.TemporaryDirectory(prefix="hq-browser-") as folder:
        url = "sqlite:///" + str(Path(folder) / "browser.db")
        old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        engine, sessions = session_factory(url)
        with locked(sessions) as db:
            user = User(
                id="browser-admin",
                email="browser@example.test",
                password="",
                role="admin",
                enabled=True,
            )
            db.add(user)
            token = issue(db, user, "invite", 600)
        settings = Settings(
            database_url=url,
            session_cookie_secure=False,
            gemini_enabled=False,
            dashboard_api_key="",
            analysis_api_key="",
            tradingview_webhook_key="",
            data_ingestion_key="",
            controls_reviewer_key="",
            controls_operator_key="",
            controls_broker_key="",
            _env_file=None,
        )
        app = create_app(settings)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    if httpx.get(base + "/health/live", trust_env=False).status_code == 200:
                        break
                except httpx.ConnectError:
                    time.sleep(0.1)
            env = os.environ | {
                "HQ_BROWSER_URL": base,
                "HQ_BROWSER_TOKEN": token,
                "HQ_CHROMIUM_PATH": shutil.which("chromium") or "/usr/bin/chromium",
            }
            subprocess.run(["node", "scripts/dashboard_browser_smoke.cjs"], env=env, check=True)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            app.state.engine.dispose()
            engine.dispose()
            if old_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_url
            get_settings.cache_clear()


if __name__ == "__main__":
    main()
