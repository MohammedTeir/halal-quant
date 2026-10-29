import pytest

from services.news_intelligence.external_benchmark import select_rows


def test_external_sampling_is_balanced_stable_and_does_not_change_labels():
    rows = [
        (f"{label} sentence {i}", label)
        for label in ("positive", "neutral", "negative")
        for i in range(20)
    ]
    sample = select_rows(rows, 10)
    assert sample == select_rows(list(reversed(rows)), 10)
    assert len(sample) == 30
    for label in ("positive", "neutral", "negative"):
        assert sum(actual == label for _, actual in sample) == 10
    assert set(sample) <= set(rows)


def test_identical_external_duplicates_do_not_inflate_sampling():
    rows = [("a", "positive"), ("b", "neutral"), ("c", "negative")]
    assert select_rows(rows, 1) == select_rows(rows + rows, 1)
    with pytest.raises(ValueError, match="Conflicting"):
        select_rows(rows + [("a", "negative")], 1)
    with pytest.raises(ValueError, match="support"):
        select_rows(rows, 2)
