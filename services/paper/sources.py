"""Periodic read-only source acquisition into the fact ledger, never trading authority."""

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

from apps.api.db import utcnow
from packages.config.settings import get_settings
from services.paper.schemas import OpenAccount

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = {
    "NEWS_PROVIDER": "finnhub",
    "CALENDAR_PROVIDER": "bls",
    "FOMC_PROVIDER": "federal_reserve",
    "EARNINGS_PROVIDER": "finnhub_earnings",
}


def jobs(account, now):
    """Only fixed existing adapters; no caller-selected modules, URLs or credentials."""
    if account.mode != "forward" or any(
        account.asset_classes.get(s, "stock") != "stock" for s in account.universe
    ):
        raise ValueError("Source workflow currently supports forward stock accounts only")
    today = now.date()
    start = (today - timedelta(days=2)).isoformat()
    end = (today + timedelta(days=7)).isoformat()
    result = [("bls", "services.macro_intelligence.acquire_bls", [])]
    for year in sorted({today.year, (today + timedelta(days=7)).year}):
        result.append(
            (f"fomc-{year}", "services.macro_intelligence.acquire_fomc", ["--year", str(year)])
        )
    for symbol in account.universe:
        ticker = account.provider_symbols.get(symbol, symbol)
        # Existing fact adapters scope facts by ticker; aliases need an explicit
        # normalization implementation rather than silently importing the wrong scope.
        if ticker != symbol:
            raise ValueError("Source workflow requires internal symbols equal to provider tickers")
        result.extend(
            [
                (
                    "news-" + ticker,
                    "services.market_data.acquire_news",
                    [
                        "--symbol",
                        ticker,
                        "--asset-class",
                        "stock",
                        "--start",
                        start,
                        "--end",
                        today.isoformat(),
                    ],
                ),
                (
                    "earnings-" + ticker,
                    "services.macro_intelligence.acquire_earnings",
                    ["--symbol", ticker, "--start", start, "--end", end],
                ),
                (
                    "actions-" + ticker,
                    "services.market_data.acquire_actions",
                    ["--symbol", ticker, "--asset-class", "stock", "--start", start, "--end", end],
                ),
            ]
        )
    return result


def execute(command, stop):
    """Bound the child; never echo stderr, responses, config or credentials."""
    with subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as child:
        deadline = time.monotonic() + 120
        while child.poll() is None:
            if stop.wait(0.2) or time.monotonic() >= deadline:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                return False
        return child.returncode == 0


def poll(account, archive, stop, *, run=execute, now=None, progress=None):
    now = now or utcnow()
    plan = jobs(account, now)
    if (
        archive.exists()
        and sum(p.stat().st_size for p in archive.rglob("*") if p.is_file()) >= 512 * 1024 * 1024
    ):
        raise ValueError(
            "Archive budget reached; preserve and move archives off-device before continuing"
        )
    folder = archive / (now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    results = []
    for index, (name, module, arguments) in enumerate(plan, 1):
        if stop.is_set():
            break
        if progress:
            progress(f"[{index}/{len(plan)}] {name}: reading source and saving observations…")
        ok = run([sys.executable, "-m", module, *arguments, "--archive", str(folder / name)], stop)
        results.append({"source": name, "status": "IMPORTED" if ok else "FAILED"})
        if progress:
            progress(f"[{index}/{len(plan)}] {name}: {results[-1]['status']}")
    result = {
        "status": "OBSERVATIONS_IMPORTED"
        if len(results) == len(plan) and all(r["status"] == "IMPORTED" for r in results)
        else "INCOMPLETE",
        "started_at": now.isoformat(),
        "finished_at": utcnow().isoformat(),
        "results": results,
        "expected_polls": len(plan),
        "scope": "Acquisition outcomes only; not complete source coverage, classification, screening or execution approval",
        "orders_submitted": 0,
        "messages_sent": 0,
    }
    (folder / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    temporary = archive / (".latest-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(archive / "latest.json")
    return result


def single_poll(account, archive, *, stop=None, progress=None):
    archive = archive.resolve()
    archive.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (archive / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return poll(account, archive, stop or threading.Event(), progress=progress)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-file", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=Path("data/paper-sources"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()
    if not 300 <= args.interval_seconds <= 600:
        parser.error("Use 300..600 seconds; stale polls still fail existing entry gates")
    os.umask(0o077)
    stop = threading.Event()
    previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, lambda *_: stop.set())
    try:
        settings = get_settings()
        if "database_url" not in settings.model_fields_set:
            raise ValueError("Explicit private database configuration required")
        if not all(
            (
                settings.alpaca_api_key.get_secret_value(),
                settings.alpaca_secret_key.get_secret_value(),
                settings.finnhub_api_key.get_secret_value(),
            )
        ):
            raise ValueError("Configure read-only source credentials first")
        account = OpenAccount.model_validate_json(args.account_file.read_text())
        jobs(account, utcnow())
        args.archive = args.archive.resolve()
        args.archive.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (args.archive / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            while not stop.is_set():
                try:
                    result = poll(account, args.archive, stop)
                except (ValueError, OSError):
                    result = {
                        "status": "INCOMPLETE",
                        "error": "LOCAL_ARCHIVE_UNAVAILABLE_OR_BUDGET_REACHED",
                        "orders_submitted": 0,
                        "messages_sent": 0,
                    }
                print(json.dumps(result), flush=True)
                if args.once:
                    parser.exit(0 if result["status"] == "OBSERVATIONS_IMPORTED" else 1)
                stop.wait(args.interval_seconds)
    except (ValueError, OSError):
        parser.exit(
            1,
            "Source worker unavailable: check private configuration, input file and existing local worker.\n",
        )
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
