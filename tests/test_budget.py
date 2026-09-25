import pytest

from contratoclaro.budget import BudgetExceeded, BudgetLedger


def test_reservation_blocks_calls_before_limit_is_exceeded(tmp_path):
    ledger = BudgetLedger(tmp_path / "cost.db", limit_usd=0.01)
    ledger.reserve(0.008, "first")
    with pytest.raises(BudgetExceeded):
        ledger.reserve(0.003, "second")


def test_actual_usage_replaces_reservation_and_survives_restart(tmp_path):
    path = tmp_path / "cost.db"
    ledger = BudgetLedger(path, limit_usd=1)
    key = ledger.reserve(0.1, "agent")
    ledger.settle(key, input_tokens=1000, output_tokens=100)
    assert BudgetLedger(path, limit_usd=1).total_usd == pytest.approx(0.00018)


def test_uncertain_call_keeps_its_reservation(tmp_path):
    ledger = BudgetLedger(tmp_path / "cost.db", limit_usd=1)
    ledger.reserve(0.01, "timeout")
    assert ledger.total_usd == pytest.approx(0.01)


def test_invalid_cost_is_rejected(tmp_path):
    ledger = BudgetLedger(tmp_path / "cost.db")
    for invalid in [-1, float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            ledger.reserve(invalid, "bad")


def test_cancelled_reservation_releases_budget(tmp_path):
    ledger = BudgetLedger(tmp_path / "cost.db", limit_usd=0.01)
    reservation = ledger.reserve(0.01, "failed-call")
    ledger.cancel(reservation)
    assert ledger.total_usd == 0
    ledger.reserve(0.01, "next-call")
