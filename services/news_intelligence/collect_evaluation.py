"""Collect a frozen Gemini evaluation once into an exclusive run directory.

This explicitly invokes the configured backend provider and can consume quota.
A started case is never automatically resumed or regenerated after a crash.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from packages.config.settings import get_settings
from services.news_intelligence.classification import build_target_prompt
from services.news_intelligence.evaluation import Corpus
from services.news_intelligence.providers.gemini import GeminiAdapter, GeminiError


def _write(path, value):
    with path.open("x") as output:
        json.dump(value, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")


def collect(
    corpus_path: Path,
    run_dir: Path,
    adapter,
    model_name: str,
    *,
    prompt_version="news-classification-v2",
):
    if prompt_version not in ("news-classification-v2", "news-classification-v3"):
        raise ValueError("Unknown evaluation prompt version")
    raw = corpus_path.read_bytes()
    corpus = Corpus.model_validate_json(raw)
    if len(corpus.cases) > 100:
        raise ValueError("A live evaluation is limited to 100 cases per explicit run")
    # Exclusive directory is a durable claim. Re-running this path never recalls Gemini.
    run_dir.mkdir(parents=True, exist_ok=False)
    checksum = hashlib.sha256(raw).hexdigest()
    _write(
        run_dir / "manifest.json",
        {
            "corpus_sha256": checksum,
            "model_name": model_name,
            "prompt_version": prompt_version,
            "started_at": datetime.now(UTC).isoformat(),
            "case_count": len(corpus.cases),
            "origin": "live",
            "automatic_resume": False,
        },
    )
    # Persist the exact input for independent later review.
    (run_dir / "corpus.json").write_bytes(raw)
    outputs, versions = {}, set()
    for index, case in enumerate(corpus.cases):
        # Filenames use an index, never caller-supplied case IDs/paths.
        _write(run_dir / f"{index:04d}-started.json", {"case_id": case.case_id})
        started = monotonic()
        try:
            completion = adapter.complete(
                build_target_prompt([case.source()], case.target(), version=prompt_version)
            )
        except GeminiError as error:
            _write(
                run_dir / f"{index:04d}-result.json",
                {
                    "case_id": case.case_id,
                    "status": "FAILED",
                    "code": error.code,
                    "elapsed_seconds": round(monotonic() - started, 3),
                },
            )
            # Stop on provider errors instead of repeatedly consuming quota on remaining cases.
            break
        outputs[case.case_id] = completion.text
        versions.add(completion.model_version)
        _write(
            run_dir / f"{index:04d}-result.json",
            {
                "case_id": case.case_id,
                "status": "COMPLETED",
                "model_version": completion.model_version,
                "usage": completion.usage,
                "elapsed_seconds": round(monotonic() - started, 3),
                "raw_output": completion.text,
            },
        )
    # Model-version drift cannot be represented as a homogeneous quality run.
    if len(versions) > 1:
        raise ValueError(
            "Provider model version changed during evaluation; inspect per-case records"
        )
    result = {
        "corpus_sha256": checksum,
        "model_name": model_name,
        "model_version": next(iter(versions), "unavailable"),
        "prompt_version": prompt_version,
        "origin": "live",
        "outputs": outputs,
    }
    _write(run_dir / "responses.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--prompt-version",
        choices=("news-classification-v2", "news-classification-v3"),
        default="news-classification-v3",
    )
    parser.add_argument("--timeout-seconds", type=float, default=60)
    args = parser.parse_args()
    try:
        if not 0.1 <= args.timeout_seconds <= 120:
            parser.error("Evaluation timeout must be 0.1..120 seconds")
        # Process-local evaluation deadline: do not modify published settings.
        settings = get_settings().model_copy(
            update={"gemini_timeout_seconds": args.timeout_seconds}
        )
        result = collect(
            args.corpus,
            args.run_dir,
            GeminiAdapter(settings),
            settings.gemini_model,
            prompt_version=args.prompt_version,
        )
        expected = len(Corpus.model_validate_json(args.corpus.read_bytes()).cases)
        if len(result["outputs"]) != expected:
            parser.exit(
                1, "Incomplete evaluation; preserve the run and score missing cases as failures\n"
            )
    except GeminiError as error:
        parser.exit(1, error.code + "\n")
    except (ValueError, OSError):
        parser.exit(1, "Evaluation collection failed; preserve and inspect the run directory\n")
    print("Evaluation responses saved; score them with services.news_intelligence.evaluation")


if __name__ == "__main__":
    main()
