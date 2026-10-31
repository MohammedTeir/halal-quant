"""Prepare an unapproved paper campaign; optional private source setup and proposal submission."""

import argparse
import getpass
import hashlib
import json
import os
import sys
import warnings
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values, set_key

from apps.api.db import utcnow
from packages.config.settings import get_settings
from packages.schemas.control_operations import MethodologyApproval
from services.paper.schemas import ForwardProtocol, OpenAccount
from services.paper.sources import PROVIDERS, ROOT, single_poll

METHODOLOGY = "paper-equity-screen-proposal-v1"
FEEDS = {
    "news": "finnhub",
    "calendar": "bls",
    "fomc": "federal_reserve",
    "earnings": "finnhub_earnings",
    "corporate_actions": "alpaca_iex",
}
REFERENCE = "https://github.com/MohammedTeir/halal-quant/blob/main/docs/data-providers.md"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def prepare(folder, now=None):
    now = now or utcnow()
    if folder.exists():
        manifest = json.loads((folder / "manifest.json").read_text())
        if set(manifest) != {
            "account.json",
            "protocol.json",
            "methodology-proposal.json",
            "review.md",
        }:
            raise ValueError("Unexpected setup manifest")
        for name, checksum in manifest.items():
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != checksum:
                raise ValueError("Prepared files changed; preserve them and use a fresh directory")
        return manifest
    account = OpenAccount.model_validate_json(
        (ROOT / "examples/paper/largecap-account-draft.json").read_text()
    )
    policy = account.policy.model_copy(
        update={
            "version": account.account_id + "-policy-v1",
            "methodology": METHODOLOGY,
            "fee_per_order": Decimal(1),
            "slippage_bps": Decimal(5),
        }
    )
    account = OpenAccount.model_validate(account.model_dump() | {"policy": policy})
    review = """# DRAFT: paper campaign evidence review

This is an AI-prepared technical proposal, not independent human, qualified
Shariah or source-completeness approval. No stock is approved by this file.

Proposed equity rules: business activity review; debt and interest assets each
strictly below 30% of a documented average market-cap denominator; impure revenue
strictly below 5% of total revenue; explicit purification and disposition guidance.
These proposed parameters are not a certification of AAOIFI compliance. The
current software does not specify the averaging window; it must be documented
and reviewed with source statements before any financial screen can pass.
Missing denominator history, business/impure-income facts or possession evidence
remain missing; no zero values or true approval flags are inferred.

Sources: Alpaca IEX quotes/calendar and split/dividend observations; Finnhub
company news and date-only earnings; official BLS schedule and Federal Reserve
FOMC calendar. IEX is a subset of market activity. A successful poll is not proof
of complete coverage. BLS is not a comprehensive economic calendar. Corporate
announcements may not be available before their effective date. Raw timestamps,
first-observation semantics, entitlements, rates and missing facts need review.
News still needs grounded classification and fresh stored strategy decisions.

Campaign: internal cash simulator, ten candidate stocks, 100000 virtual USD,
1 USD/order and 5 basis points slippage as explicit proposed cost assumptions,
whole shares, no external orders, no leverage/shorting, regular sessions only,
simulated T+1 settlement. Default protocol: 20 complete sessions and at least
20 actual elapsed days, ten completed exits, controlled restart recovery, flat
settled final state and no critical violations. These are proposed criteria.

References:
https://aaoifi.com/
https://docs.alpaca.markets/docs/about-market-data-api
https://finnhub.io/docs/api
https://www.bls.gov/schedule/news_release/
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
"""
    checksum = hashlib.sha256(review.encode()).hexdigest()
    evidence = {
        "evidence_id": "paper-proposal-" + checksum[:20],
        "provider": "technical_proposal",
        "document_sha256": checksum,
        "observed_at": now,
        "recorded_at": now,
        "effective_at": now,
        "expires_at": now + timedelta(days=60),
    }
    methodology = MethodologyApproval(
        record_id=METHODOLOGY + "-draft-v1",
        methodology_id=METHODOLOGY,
        status="PENDING",
        evidence=evidence,
        denominator="average_market_cap",
        maximum_debt_ratio="0.30",
        maximum_interest_assets_ratio="0.30",
        maximum_impure_income_ratio="0.05",
        ratio_boundary="strictly_below",
        divestment_guidance="Qualified review must define disposition and purification; no automatic religious ruling.",
        note="AI-prepared pending technical proposal; source figures, averaging window, business activity and qualified screening are not verified.",
        references=["https://aaoifi.com/", REFERENCE],
    )
    protocol = ForwardProtocol(
        run_id=account.account_id + "-run-v1",
        account_id=account.account_id,
        feed_providers=FEEDS,
        data_review={p: checksum for p in {"alpaca_iex", *FEEDS.values()}},
        source_limitations="DRAFT technical review only. IEX is partial; BLS is not comprehensive; source completeness, news classification and instrument screening remain unverified. See the bound review document.",
        references=[REFERENCE, "https://aaoifi.com/"],
    )
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    (folder / "review.md").write_text(review)
    for name, value in (
        ("account.json", account),
        ("protocol.json", protocol),
        ("methodology-proposal.json", methodology),
    ):
        write_json(folder / name, value.model_dump(mode="json"))
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    write_json(folder / "manifest.json", manifest)
    return manifest


def hidden(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except (getpass.GetPassWarning, EOFError):
            raise ValueError("A private interactive terminal is required") from None


def configure(path, *, prompt=hidden):
    values = dotenv_values(path)
    # Validate all conflicts before writing anything. Do not replace a selected provider.
    for key, provider in PROVIDERS.items():
        if values.get(key) not in (None, "", provider) or os.environ.get(key, provider) not in (
            "",
            provider,
        ):
            raise ValueError("Existing source selection differs; preserve it for review")
    settings = get_settings()
    token = None
    if not settings.finnhub_api_key.get_secret_value():
        token = prompt("Finnhub API key (hidden, saved only in your private .env): ").strip()
        if not token:
            raise ValueError("Finnhub key is required for company news and earnings")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    for key, provider in PROVIDERS.items():
        set_key(path, key, provider, quote_mode="never")
    if token:
        set_key(path, "FINNHUB_API_KEY", token)
    get_settings.cache_clear()


class SubmissionError(ValueError):
    """Static actionable message, without remote response bodies or credentials."""


def check_response(response, stage):
    if 200 <= response.status_code < 300:
        return
    hints = {
        401: "Check the operator email/password and that the invitation was accepted.",
        403: "Check the operator role and session/CSRF access.",
        409: "An immutable account/run ID conflicts. Preserve drafts; do not overwrite existing records.",
        422: "Enter the full operator email and password; ensure the invitation was accepted."
        if stage == "login"
        else "The server rejected the proposal contract. Preserve the draft for diagnosis.",
        429: "Login or API rate limit reached. Wait before retrying.",
        503: "Check PAPER_TRADING_ENABLED and PAPER_FORWARD_ENABLED on Render, redeploy, and verify database readiness.",
    }
    raise SubmissionError(
        f"{stage.upper()}_HTTP_{response.status_code}: "
        + hints.get(response.status_code, "Check deployment availability and current API version.")
    )


def submit(folder, origin, email, password, *, transport=None):
    """Use ordinary operator auth/CSRF; never reviewer endpoints or order routes."""
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use the HTTPS dashboard origin without a path or credentials")
    with httpx.Client(
        base_url=origin.rstrip("/"), timeout=30, follow_redirects=False, transport=transport
    ) as client:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        check_response(response, "login")
        try:
            identity = response.json()
            headers = {"X-CSRF-Token": identity["csrf"], "Origin": origin.rstrip("/")}
            if identity["user"]["role"] != "operator":
                raise SubmissionError(
                    "OPERATOR_ROLE_REQUIRED: An operator login is required; administrator rights are separate"
                )
            results = []
            for filename, route in (("account.json", "accounts"), ("protocol.json", "runs")):
                response = client.post(
                    "/api/v1/paper/" + route,
                    json=json.loads((folder / filename).read_text()),
                    headers=headers,
                )
                check_response(response, route)
                result = response.json()
                if (
                    route == "accounts"
                    and result.get("status") not in ("CREATED", "OPENED")
                    and not result.get("account_id")
                ):
                    raise ValueError("Account was not created")
                results.append(result)
            return {
                "status": "PROPOSED_PENDING_REVIEW",
                "results": results,
                "worker_started": False,
                "orders_submitted": 0,
            }
        finally:
            # Only this temporary CLI session is logged out; preserve other devices.
            csrf = locals().get("headers")
            if csrf:
                try:
                    client.post("/api/v1/auth/logout", headers=csrf)
                except httpx.HTTPError:
                    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/paper-setup"))
    parser.add_argument("--configure-sources", action="store_true")
    parser.add_argument("--poll", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--origin", default="https://halal-quant.vercel.app")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        manifest = prepare(args.output.resolve())
        if args.configure_sources:
            configure(ROOT / ".env")
        summary = {
            "status": "DRAFT_PREPARED",
            "files": sorted(manifest),
            "approved": False,
            "orders_submitted": 0,
            "messages_sent": 0,
        }
        if args.poll:
            account = OpenAccount.model_validate_json((args.output / "account.json").read_text())
            settings = get_settings()
            if "database_url" not in settings.model_fields_set:
                raise ValueError("Explicit private database configuration required")
            print(
                "Polling sources sequentially; this can take several minutes. Retry submission with --submit alone to skip these polls.",
                file=sys.stderr,
                flush=True,
            )
            summary["sources"] = single_poll(
                account,
                ROOT / "data/paper-sources",
                progress=lambda message: print(message, file=sys.stderr, flush=True),
            )
        if args.submit:
            email = input("Operator email: ").strip()
            password = hidden("Operator password (hidden): ")
            summary["proposal"] = submit(args.output, args.origin, email, password)
        print(json.dumps(summary))
    except SubmissionError as error:
        parser.exit(
            1,
            str(error)
            + "\nRetry with --submit only; source polling does not need to repeat. No approval was created.\n",
        )
    except httpx.RequestError:
        parser.exit(
            1,
            "NETWORK_UNAVAILABLE: The API request timed out or could not connect. Check Render readiness, then retry with --submit only. No automatic retry was sent.\n",
        )
    except KeyboardInterrupt:
        parser.exit(
            130,
            "Preparation interrupted. Preserve generated files; retry with --submit only if source polling already finished.\n",
        )
    except (ValueError, OSError, KeyError, EOFError, httpx.HTTPError):
        parser.exit(
            1,
            "Preparation not completed. Preserve generated files; check private credentials, source settings, operator role and enabled API flags. No approval was created.\n",
        )


if __name__ == "__main__":
    main()
