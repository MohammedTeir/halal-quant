"""Prepare a hash-bound blind label packet and a separate model-results packet.

This is review preparation, not reviewer authentication or automatic approval.
"""

import argparse
import hashlib
import json
from pathlib import Path

from services.news_intelligence.evaluation import Corpus, Responses, evaluate_corpus


def prepare(corpus_path: Path, freeze_path: Path, responses_path: Path, output: Path):
    raw = corpus_path.read_bytes()
    corpus = Corpus.model_validate_json(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    freeze_raw = freeze_path.read_bytes()
    freeze = json.loads(freeze_raw)
    responses_raw = responses_path.read_bytes()
    responses = Responses.model_validate_json(responses_raw)
    if freeze["corpus_sha256"] != checksum or not freeze["labels_frozen_before_generation"]:
        raise ValueError("Review freeze does not match the corpus")
    score = evaluate_corpus(corpus, responses, checksum)
    sources = {source["id"]: source for source in freeze["sources"]}
    if len(sources) != len(freeze["sources"]):
        raise ValueError("Duplicate review source IDs")
    originals = {case.case_id for case in corpus.cases if not case.attack}
    if set(sources) != originals:
        raise ValueError("Every real-source case needs exact source-review provenance")
    for case in corpus.cases:
        if (
            not case.attack
            and hashlib.sha256(case.summary.encode()).hexdigest()
            != sources[case.case_id]["excerpt_sha256"]
        ):
            raise ValueError("Review excerpt hash mismatch")
    # Exclusive creation prevents overwriting an existing review or failed run.
    output.mkdir(parents=True, exist_ok=False)

    def write(name, value):
        (output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    # Review this before opening results, and record any disagreements unchanged.
    write("blind-labels.json", {"corpus": corpus.model_dump(mode="json"), "source_review": freeze})
    write("model-results.json", {"responses": responses.model_dump(mode="json"), "score": score})
    write(
        "review-form.json",
        {
            "status": "PENDING",
            "reviewer_name": None,
            "reviewed_at": None,
            "independent_of_implementation_author": None,
            "labels_reviewed_before_model_results": None,
            "source_suitability_approved": None,
            "labels_approved": None,
            "sample_representativeness_approved": None,
            "disagreements": [],
            "corpus_sha256": checksum,
            "freeze_sha256": hashlib.sha256(freeze_raw).hexdigest(),
            "responses_sha256": hashlib.sha256(responses_raw).hexdigest(),
            "authorized_for_entry": False,
        },
    )
    (output / "README.md").write_text(
        "# Independent review packet\n\n"
        "1. Review blind-labels.json against the linked primary sources before opening model-results.json.\n"
        "2. Record label disagreements, publisher limitations, source suitability and missing sample categories.\n"
        "3. Inspect model-results.json, including failed and missing cases, without changing the frozen labels.\n"
        "4. Complete review-form.json with your identity, independence, date and decisions; retain all originals.\n\n"
        "An author-filled form does not establish independent approval. This packet does not authenticate "
        "reviewer identity, certify representative accuracy, or authorize trading.\n"
    )
    return score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "freeze", "responses", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.corpus, args.freeze, args.responses, args.output)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
