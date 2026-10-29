import hashlib
import json

import pytest

from services.news_intelligence.review_packet import prepare
from tests.decision.test_evaluation import CORPUS, fixture_responses


def files(tmp_path):
    corpus, responses, digest = fixture_responses()
    freeze = tmp_path / "freeze.json"
    freeze.write_text(
        json.dumps(
            {
                "corpus_sha256": digest,
                "labels_frozen_before_generation": True,
                "sources": [
                    {
                        "id": case.case_id,
                        "excerpt_sha256": hashlib.sha256(case.summary.encode()).hexdigest(),
                    }
                    for case in corpus.cases
                    if not case.attack
                ],
            }
        )
    )
    outputs = tmp_path / "responses.json"
    outputs.write_text(responses.model_dump_json())
    return freeze, outputs


def test_packet_separates_blind_review_and_never_claims_approval(tmp_path):
    freeze, responses = files(tmp_path)
    output = tmp_path / "packet"
    prepare(CORPUS, freeze, responses, output)
    blind = json.loads((output / "blind-labels.json").read_bytes())
    assert "responses" not in blind and "score" not in blind
    form = json.loads((output / "review-form.json").read_bytes())
    assert form["status"] == "PENDING" and form["reviewer_name"] is None
    assert not form["authorized_for_entry"]
    with pytest.raises(FileExistsError):
        prepare(CORPUS, freeze, responses, output)


@pytest.mark.parametrize("change", ["corpus_hash", "excerpt_hash", "source_missing"])
def test_packet_rejects_unbound_or_incomplete_review_evidence(tmp_path, change):
    freeze, responses = files(tmp_path)
    data = json.loads(freeze.read_bytes())
    if change == "corpus_hash":
        data["corpus_sha256"] = "0" * 64
    elif change == "excerpt_hash":
        data["sources"][0]["excerpt_sha256"] = "0" * 64
    else:
        data["sources"].pop()
    freeze.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        prepare(CORPUS, freeze, responses, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()
