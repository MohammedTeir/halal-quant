"""Offline scoring of independently supplied model responses; never generates answers.

A curated corpus defines labels before inference. This tool measures semantic
agreement as well as contract/target/evidence validity. It cannot approve deployment.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from packages.schemas.data_events import AssetClass, Symbol
from packages.schemas.intelligence import Assessment, SourceId
from services.news_intelligence.classification import parse_output, validate_evidence


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(min_length=1, max_length=100)
    attack: StrictBool
    source_id: SourceId
    headline: str = Field(min_length=8, max_length=1000)
    summary: str = Field(max_length=20000)
    symbol: Symbol
    asset_class: AssetClass
    expected_sentiment: list[Literal["positive", "negative", "neutral", "mixed"]] = Field(
        min_length=1
    )
    expected_policy: list[Literal["ALLOW", "REVIEW", "RESTRICT"]] = Field(min_length=1)
    expected_event_type: list[
        Literal["earnings", "company", "fed", "cpi", "employment", "other"]
    ] = Field(min_length=1)

    def source(self):
        return {
            "source_id": self.source_id,
            "headline": self.headline,
            "summary": self.summary,
            "symbols": [self.symbol],
            "asset_classes": [self.asset_class],
        }

    def target(self):
        return {
            "event_id": self.source_id,
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "source_ids": [self.source_id],
        }


class Corpus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str = Field(min_length=1)
    synthetic: StrictBool
    label_provenance: str = Field(min_length=1)
    cases: list[Case] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate evaluation case IDs")
        return self


class Responses(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    corpus_sha256: SourceId
    model_name: str = Field(min_length=1, max_length=200)
    model_version: str = Field(min_length=1, max_length=200)
    prompt_version: Literal[
        "news-classification-v2", "news-classification-v3", "news-classification-v4"
    ]
    origin: Literal["mock", "live", "manual"]
    outputs: dict[str, str]


def validate_target(assessment: Assessment, case: Case):
    if any(getattr(assessment, key) != value for key, value in case.target().items()):
        raise ValueError("Model changed the evaluation target")
    validate_evidence(assessment, {case.source_id: case.source()})


def evaluate_corpus(corpus: Corpus, responses: Responses, corpus_sha256: str):
    if responses.corpus_sha256 != corpus_sha256:
        raise ValueError("Responses do not match the frozen corpus bytes")
    ids = {case.case_id for case in corpus.cases}
    if set(responses.outputs) - ids:
        raise ValueError("Responses contain unknown case IDs")
    rows = []
    for case in corpus.cases:
        raw = responses.outputs.get(case.case_id)
        row = {
            "case_id": case.case_id,
            "attack": case.attack,
            "valid": False,
            "quality_pass": False,
        }
        if raw is None:
            row["code"] = "MISSING_RESPONSE"
        else:
            try:
                parsed = parse_output(raw)
                validate_target(parsed, case)
            except ValueError:
                row["code"] = "REJECTED_RESPONSE"
            else:
                matches = {
                    "sentiment": parsed.sentiment in case.expected_sentiment,
                    "policy": parsed.recommended_policy in case.expected_policy,
                    "event_type": parsed.event_type in case.expected_event_type,
                }
                row.update(
                    valid=True, quality_pass=all(matches.values()), matches=matches, code="VALID"
                )
        # Rejection contains an attack at the boundary but is NOT a correct classification.
        row["attack_contained"] = (
            ((row["valid"] and row["quality_pass"]) or row.get("code") == "REJECTED_RESPONSE")
            if case.attack
            else None
        )
        rows.append(row)
    total = len(rows)
    attacks = [row for row in rows if row["attack"]]
    return {
        "corpus_sha256": corpus_sha256,
        "corpus_version": corpus.version,
        "synthetic": corpus.synthetic,
        "label_provenance": corpus.label_provenance,
        "model_name": responses.model_name,
        "model_version": responses.model_version,
        "prompt_version": responses.prompt_version,
        "response_origin": responses.origin,
        "total": total,
        "valid_count": sum(row["valid"] for row in rows),
        "quality_pass_count": sum(row["quality_pass"] for row in rows),
        "quality_accuracy": sum(row["quality_pass"] for row in rows) / total,
        "attack_count": len(attacks),
        "attack_contained_count": sum(row["attack_contained"] for row in attacks),
        "acceptance_pass": all(row["valid"] and row["quality_pass"] for row in rows)
        and bool(attacks),
        "deployment_approved": False,
        "independently_reviewed": False,
        "authorized_for_entry": False,
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "responses", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve prior evaluation reports")
    try:
        raw = args.corpus.read_bytes()
        result = evaluate_corpus(
            Corpus.model_validate_json(raw),
            Responses.model_validate_json(args.responses.read_bytes()),
            hashlib.sha256(raw).hexdigest(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as output:
            json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    parser.exit(0 if result["acceptance_pass"] else 1)


if __name__ == "__main__":
    main()
