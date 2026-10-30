"""Strict local research evidence; receipt time prevents retrospective authority."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ReplayEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    revision_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    kind: Literal["compliance", "news", "macro"]
    state: Literal["ALLOW", "BLOCK"]
    published_at: AwareDatetime
    received_at: AwareDatetime
    effective_at: AwareDatetime
    expires_at: AwareDatetime
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def dates(self):
        if self.received_at < self.published_at or self.expires_at <= self.effective_at:
            raise ValueError("Invalid evidence receipt or validity window")
        return self


def validate_replay(records):
    if len({r.revision_id for r in records}) != len(records):
        raise ValueError("Replay revision IDs must be unique")
    # Receipt ties have no reliable order; do not let JSON ordering choose truth.
    keys = [(r.scope, r.kind, r.received_at) for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError("Ambiguous replay receipt order")


def replay_gate(records, symbol, at):
    blockers, refs = [], {}
    for scope, kind in [(symbol, "compliance"), (symbol, "news"), ("MARKET", "macro")]:
        known = [
            r
            for r in records
            if r.scope == scope
            and r.kind == kind
            and r.published_at <= at
            and r.received_at <= at
            and r.effective_at <= at
        ]
        latest = max(known, key=lambda r: r.received_at) if known else None
        if latest:
            refs[kind] = latest.revision_id
        if latest is None or latest.expires_at <= at or latest.state != "ALLOW":
            blockers.append(kind.upper() + "_MISSING_EXPIRED_OR_BLOCKED")
    return blockers, refs
