"""Prepare and score a noncommercial research check against external human labels.

FinancialPhraseBank is not production news, a trading signal, or project approval.
Corpus text and provider outputs stay in the explicitly selected local directory.
"""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from services.news_intelligence.evaluation import Corpus, Responses, evaluate_corpus

ARCHIVE_SHA256 = "0e1a06c4900fdae46091d031068601e3773ba067c7cecb5b0da1dcba5ce989a6"
MEMBER = "FinancialPhraseBank-v1.0/Sentences_AllAgree.txt"
LABELS = ("negative", "neutral", "positive")
SEED = "halal-quant-external-labels-v1-20261029"


def select_rows(rows, per_label):
    if not 1 <= per_label <= 30:
        raise ValueError("Choose 1..30 cases per label")
    selected = []
    seen = {}
    for text, label in rows:
        if label not in LABELS or not text.strip():
            raise ValueError("Invalid benchmark row")
        if text in seen and seen[text] != label:
            raise ValueError("Conflicting external labels")
        seen[text] = label
    for label in LABELS:
        group = [(text, actual) for text, actual in seen.items() if actual == label]
        if len(group) < per_label:
            raise ValueError("Insufficient label support")
        group.sort(key=lambda row: hashlib.sha256((SEED + row[0]).encode()).hexdigest())
        selected.extend(group[:per_label])
    return selected


def freeze_archive(archive: Path, output: Path, per_label=10):
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Unexpected benchmark archive; verify provenance before changing the hash")
    with ZipFile(archive) as z:
        info = z.getinfo(MEMBER)
        if info.file_size > 1024 * 1024:
            raise ValueError("Unexpected benchmark size")
        data = z.read(info).decode("latin1")
        license_text = z.read("FinancialPhraseBank-v1.0/License.txt").decode()
    rows = [tuple(line.rsplit("@", 1)) for line in data.splitlines() if line.strip()]
    cases = []
    for index, (text, label) in enumerate(select_rows(rows, per_label)):
        digest = hashlib.sha256(text.encode()).hexdigest()
        cases.append(
            {
                "case_id": f"fpb-{index:03}",
                "attack": False,
                "source_id": digest,
                "headline": "External financial-news sentiment research case",
                "summary": text,
                "symbol": "EVAL_ONLY",
                "asset_class": "stock",
                "expected_sentiment": [label],
                # Only sentiment labels originate from the independent human annotators.
                "expected_event_type": ["earnings", "company", "other", "fed", "cpi", "employment"],
                "expected_policy": ["ALLOW", "REVIEW", "RESTRICT"],
            }
        )
    corpus = Corpus.model_validate(
        {
            "version": "financial-phrasebank-allagree-research-v1",
            "synthetic": False,
            "label_provenance": "External original human sentiment labels, all annotators agree. Fixed hash-ranked stratified sample. EVAL_ONLY is a synthetic evaluation target, not an issuer/ticker claim. Policy/event labels are unconstrained and not independently annotated. Noncommercial research only; no production approval.",
            "cases": cases,
        }
    )
    output.mkdir(parents=True, exist_ok=False)
    corpus_path = output / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json(indent=2) + "\n")
    manifest = {
        "archive_sha256": ARCHIVE_SHA256,
        "member": MEMBER,
        "source_rows": len(rows),
        "unique_texts": len({text for text, _ in rows}),
        "duplicate_handling": "Identical text/label pairs sampled once; conflicting labels rejected",
        "per_label": per_label,
        "selection_seed": SEED,
        "selection_method": "sha256(seed + text), lowest per label",
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "source_url": "https://huggingface.co/datasets/takala/financial_phrasebank",
        "paper_url": "https://arxiv.org/abs/1307.5336",
        "attribution": "Malo, Sinha, Takala, Korhonen and Wallenius (2013), FinancialPhraseBank v1.0",
        "license": "CC BY-NC-SA 3.0; retained original license and README terms",
        "noncommercial_research_only": True,
        "independent_human_sentiment_labels": True,
        "project_human_signoff": False,
        "threshold_frozen_before_predictions": {
            "minimum_sentiment_accuracy": 0.9,
            "all_responses_valid": True,
        },
        "limits": [
            "OMX Helsinki financial news, not representative US/ETF/gold news",
            "Pretraining overlap unknown",
            "Individual publisher URLs/receipt timestamps unavailable",
            "No independent event/policy/attack labels",
        ],
        "authorized_for_entry": False,
    }
    (output / "freeze.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "License.txt").write_text(license_text)
    return manifest


def score(corpus_path: Path, responses_path: Path, freeze_path: Path):
    raw = corpus_path.read_bytes()
    freeze = json.loads(freeze_path.read_bytes())
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != freeze["corpus_sha256"]:
        raise ValueError("Frozen benchmark bytes changed")
    corpus = Corpus.model_validate_json(raw)
    responses = Responses.model_validate_json(responses_path.read_bytes())
    report = evaluate_corpus(corpus, responses, checksum)
    # This non-adversarial external-label check never replaces the attack gate.
    report["external_sentiment_gate_pass"] = (
        report["valid_count"] == report["total"] and report["quality_accuracy"] >= 0.9
    )
    report["external_label_provenance"] = freeze
    report["responses_sha256"] = hashlib.sha256(responses_path.read_bytes()).hexdigest()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("freeze")
    prepare.add_argument("--archive", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--per-label", default=10, type=int)
    scoring = commands.add_parser("score")
    for name in ("corpus", "responses", "freeze", "output"):
        scoring.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            freeze_archive(args.archive, args.output, args.per_label)
        else:
            result = score(args.corpus, args.responses, args.freeze)
            with args.output.open("x") as f:
                json.dump(result, f, indent=2, allow_nan=False)
                f.write("\n")
            parser.exit(0 if result["external_sentiment_gate_pass"] else 1)
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
