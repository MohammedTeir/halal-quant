# Research evidence

`synthetic-smoke.json` records execution counts and run identities from the first
Python acceptance run. It is software evidence only, not historical returns or
proof of profitable expectancy. Full reports and input CSVs are generated locally
under ignored directories; reproduce them using [the research guide](../docs/python-research.md).

No report currently authorizes paper or live trading. Use new output filenames to
preserve prior experiments, retain source/configuration/data hashes, and document
real holdout selection before evaluating it.

`data-ingestion-smoke.json` records a real local HTTP check of synthetic fact imports,
replay/audit behavior, point-in-time exclusion, synthetic feed guard and restart
persistence. `split-audit-smoke.json` records the checked-in synthetic raw/adjusted
example's arithmetic result. Neither verifies an external provider or real data.
