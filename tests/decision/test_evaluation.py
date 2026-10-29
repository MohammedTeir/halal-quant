import hashlib
import json
from pathlib import Path

import pytest

from services.news_intelligence.collect_evaluation import collect
from services.news_intelligence.evaluation import Corpus, Responses, evaluate_corpus
from services.news_intelligence.providers.gemini import Completion, GeminiError

CORPUS = Path(__file__).resolve().parents[2] / "examples/intelligence/evaluation/corpus-v1.json"


def response(case):
    sentiment = case.expected_sentiment[0]
    return json.dumps(
        {
            "schema_version": "1.0",
            **case.target(),
            "event_type": case.expected_event_type[0],
            "sentiment": sentiment,
            "sentiment_score": {"positive": 0.6, "negative": -0.6}.get(sentiment, 0.0),
            "relevance": 0.9,
            "severity": "medium",
            "confidence": 0.8,
            "evidence": [{"source_id": case.source_id, "quote": case.headline}],
            "market_impact": "uncertain",
            "recommended_policy": case.expected_policy[0],
            "requires_human_review": True,
        }
    )


def fixture_responses():
    raw = CORPUS.read_bytes()
    corpus = Corpus.model_validate_json(raw)
    digest = hashlib.sha256(raw).hexdigest()
    responses = Responses(
        corpus_sha256=digest,
        model_name="fixture",
        model_version="fixture-v1",
        prompt_version="news-classification-v2",
        origin="mock",
        outputs={case.case_id: response(case) for case in corpus.cases},
    )
    return corpus, responses, digest


def test_evaluation_mock_success_is_never_deployment_approval():
    corpus, responses, digest = fixture_responses()
    report = evaluate_corpus(corpus, responses, digest)
    assert report["acceptance_pass"] and report["quality_accuracy"] == 1
    assert report["attack_count"] == 6 and report["response_origin"] == "mock"
    assert not report["deployment_approved"] and not report["independently_reviewed"]


@pytest.mark.parametrize(
    "failure", ["missing", "wrong_label", "wrong_target", "invented_quote", "tool", "malformed"]
)
def test_bad_classifications_reduce_quality_and_fail_acceptance(failure):
    corpus, responses, digest = fixture_responses()
    case = corpus.cases[-1]
    outputs = dict(responses.outputs)
    value = json.loads(outputs[case.case_id])
    if failure == "missing":
        outputs.pop(case.case_id)
    elif failure == "malformed":
        outputs[case.case_id] = "not JSON"
    else:
        if failure == "wrong_label":
            value["recommended_policy"] = "ALLOW"
        if failure == "wrong_target":
            value["symbol"] = "OTHER"
        if failure == "invented_quote":
            value["evidence"][0]["quote"] = "Invented unsupported evidence"
        if failure == "tool":
            value["tool_calls"] = [{"name": "place_order"}]
        outputs[case.case_id] = json.dumps(value)
    report = evaluate_corpus(corpus, responses.model_copy(update={"outputs": outputs}), digest)
    assert not report["acceptance_pass"] and report["quality_accuracy"] < 1
    attack = report["cases"][-1]
    if failure in ("missing", "wrong_label"):
        assert not attack["attack_contained"]
    else:
        assert attack["attack_contained"]  # boundary rejected; still a quality failure


def test_hash_unknown_cases_and_duplicate_corpus_ids_rejected():
    corpus, responses, digest = fixture_responses()
    with pytest.raises(ValueError, match="frozen"):
        evaluate_corpus(corpus, responses, "b" * 64)
    with pytest.raises(ValueError, match="unknown"):
        evaluate_corpus(
            corpus,
            responses.model_copy(update={"outputs": responses.outputs | {"invented": "{}"}}),
            digest,
        )
    with pytest.raises(ValueError, match="Duplicate"):
        Corpus.model_validate(corpus.model_dump() | {"cases": [corpus.cases[0], corpus.cases[0]]})


def test_collection_claims_before_call_and_never_replays_existing_run(tmp_path):
    run = tmp_path / "run"
    calls = []
    corpus, _, _ = fixture_responses()

    class Adapter:
        def complete(self, prompt):
            assert (run / "manifest.json").exists()
            assert (run / f"{len(calls):04d}-started.json").exists()
            target = json.loads(prompt["document_json"])["target"]
            case = corpus.cases[len(calls)]
            assert target == case.target()
            calls.append(prompt)
            return Completion(response(case), "gemini-fixture", {"totalTokenCount": 10})

    result = collect(CORPUS, run, Adapter(), "configured-model")
    assert len(calls) == len(corpus.cases)
    assert len(result["outputs"]) == len(corpus.cases)
    with pytest.raises(FileExistsError):
        collect(CORPUS, run, Adapter(), "configured-model")
    assert len(calls) == len(corpus.cases)


def test_collection_stops_on_provider_failure_and_preserves_claim(tmp_path):
    run = tmp_path / "failed"
    calls = []

    class Adapter:
        def complete(self, prompt):
            calls.append(prompt)
            raise GeminiError("GEMINI_RATE_LIMITED")

    result = collect(CORPUS, run, Adapter(), "configured-model")
    assert len(calls) == 1 and result["outputs"] == {}
    assert json.loads((run / "0000-result.json").read_text())["code"] == "GEMINI_RATE_LIMITED"


def test_collection_crash_keeps_started_marker_and_blocks_replay(tmp_path):
    run = tmp_path / "crash"

    class Adapter:
        def complete(self, prompt):
            raise RuntimeError("simulated crash")

    with pytest.raises(RuntimeError):
        collect(CORPUS, run, Adapter(), "configured-model")
    assert (run / "0000-started.json").exists() and not (run / "responses.json").exists()
    with pytest.raises(FileExistsError):
        collect(CORPUS, run, Adapter(), "configured-model")


def test_model_version_drift_preserves_records_without_combined_claim(tmp_path):
    run = tmp_path / "drift"
    corpus, _, _ = fixture_responses()
    calls = []

    class Adapter:
        def complete(self, prompt):
            case = corpus.cases[len(calls)]
            calls.append(case.case_id)
            return Completion(response(case), f"gemini-version-{len(calls)}", {})

    with pytest.raises(ValueError, match="version changed"):
        collect(CORPUS, run, Adapter(), "configured-model")
    assert len(calls) == len(corpus.cases)
    assert not (run / "responses.json").exists()
    assert (run / "0000-result.json").exists()


def test_attack_policy_without_human_review_is_quality_failure():
    corpus, responses, digest = fixture_responses()
    attack = next(case for case in corpus.cases if case.attack)
    outputs = dict(responses.outputs)
    value = json.loads(outputs[attack.case_id])
    value["requires_human_review"] = False
    outputs[attack.case_id] = json.dumps(value)
    report = evaluate_corpus(corpus, responses.model_copy(update={"outputs": outputs}), digest)
    row = next(row for row in report["cases"] if row["case_id"] == attack.case_id)
    assert row["valid"] and not row["quality_pass"] and not row["attack_contained"]
    assert not row["matches"]["attack_human_review"]
    assert not report["acceptance_pass"]


def test_quality_strata_expose_unrepresented_categories():
    corpus, responses, digest = fixture_responses()
    report = evaluate_corpus(corpus, responses, digest)
    for field in ("expected_event_type", "expected_sentiment"):
        for label, values in report["strata"][field].items():
            assert values["total"] == sum(label in getattr(case, field) for case in corpus.cases)
            assert values["quality_pass_count"] == values["total"]


def test_wrong_sentiment_is_quality_failure_but_safe_attack_policy_is_containment():
    corpus, responses, digest = fixture_responses()
    attack = next(case for case in corpus.cases if case.attack)
    outputs = dict(responses.outputs)
    value = json.loads(outputs[attack.case_id])
    value["sentiment"] = "negative" if "negative" not in attack.expected_sentiment else "positive"
    value["sentiment_score"] = -0.5 if value["sentiment"] == "negative" else 0.5
    outputs[attack.case_id] = json.dumps(value)
    report = evaluate_corpus(corpus, responses.model_copy(update={"outputs": outputs}), digest)
    row = next(row for row in report["cases"] if row["case_id"] == attack.case_id)
    assert row["valid"] and not row["quality_pass"] and row["attack_contained"]
    assert not report["acceptance_pass"]
