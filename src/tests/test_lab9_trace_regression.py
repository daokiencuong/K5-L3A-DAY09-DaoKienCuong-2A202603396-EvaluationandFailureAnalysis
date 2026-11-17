"""Replayable trace regression for the first bad ticket override."""
import pytest

pytestmark = pytest.mark.student


def test_ticket_override_is_first_bad_event():
    from lab9.trace_case import investigate

    broken = investigate("seeded_regression", "C-002", 55)["trial"]
    fixed = investigate("fixed", "C-002", 55)["trial"]
    broken_kinds = [event.get("kind") for event in broken["events"]]
    fixed_kinds = [event.get("kind") for event in fixed["events"]]
    assert broken_kinds.index("model_override") < broken_kinds.index("quote")
    assert "model_override" not in fixed_kinds
    assert broken["snapshot"]["refund_vnd"] == 20000
    assert fixed["snapshot"]["refund_vnd"] == 0
