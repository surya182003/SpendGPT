"""Unusual-spending detection and storage in the existing alerts table."""
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.models.alert import Alert
from app.models.transaction import Transaction
from app.services.anomaly_eval import evaluate
from app.services.anomaly_service import (
    analyse_user,
    check_new_transaction,
    check_transaction,
    detect_anomalies,
    robust_z_score,
    store_alerts,
)
from tests.conftest import category_id, make_user

NAMES = {1: "Groceries", 2: "Rent", 6: "Eating Out"}
TODAY = date(2026, 11, 20)


def txn(tid, amount, days_ago, category=1, merchant="Tesco", recurring=False):
    return SimpleNamespace(transaction_id=tid, amount=amount, merchant_name=merchant, category_id=category,
                           transaction_date=TODAY - timedelta(days=days_ago), is_recurring=recurring)


def groceries_history(n=10):
    return [txn(i, 40 + (i % 5), 100 - i * 7) for i in range(1, n + 1)]


def test_robust_z_score():
    assert robust_z_score(10, [1, 2], min_history=5) is None
    assert robust_z_score(500, [40, 41, 42, 43, 44], min_history=5) > 3.5
    assert robust_z_score(50, [50] * 6, min_history=5) == 0.0
    assert robust_z_score(120, [50] * 6, min_history=5) == float("inf")


def test_large_transaction_flagged_with_explanation_not_fraud():
    flags = check_transaction(txn(99, 180, 0), groceries_history(), NAMES)
    assert [f.type for f in flags] == ["amount_outlier"]
    flag = flags[0]
    assert flag.severity == "high" and flag.typical_amount == 42.0
    assert "Groceries" in flag.message and "4.3x" in flag.explanation
    assert "fraud" not in (flag.message + flag.explanation).lower()


def test_normal_amount_not_flagged():
    assert check_transaction(txn(99, 46, 0), groceries_history(), NAMES) == []


def test_small_excess_ignored_even_if_statistically_odd():
    history = [txn(i, 3.0 + i * 0.01, 50 - i) for i in range(1, 8)]
    assert check_transaction(txn(99, 12.0, 0), history, NAMES) == []  # only ~EUR 9 above typical


def test_insufficient_category_history_is_reported_not_judged():
    history = [txn(i, 4.0, 30 - i, category=6, merchant="Costa") for i in range(1, 12)]
    rent = txn(50, 550, 0, category=2, merchant="Landlord", recurring=True)
    assert check_transaction(rent, history, NAMES) == []  # never compares rent with coffee
    report = detect_anomalies(history + [rent], category_names=NAMES, today=TODAY)
    assert not [f for f in report.flags if f.type == "amount_outlier"]
    assert any("Rent" in note for note in report.notes)


def test_empty_history():
    report = detect_anomalies([], today=TODAY)
    assert report.flags == [] and report.history_status == "insufficient"
    assert report.transactions_analysed == 0


def test_daily_same_price_habit_is_not_a_duplicate():
    coffees = [txn(i, 4.0, 10 - i, category=6, merchant="Costa") for i in range(1, 6)]
    assert check_transaction(txn(99, 4.0, 0, category=6, merchant="Costa"), coffees, NAMES) == []


def test_possible_duplicate_but_not_for_recurring():
    history = [txn(1, 25.5, 2, merchant="Boojum", category=6)]
    flags = check_transaction(txn(2, 25.5, 1, merchant="BOOJUM", category=6), history, NAMES)
    assert [f.type for f in flags] == ["possible_duplicate"]
    recurring = check_transaction(txn(2, 25.5, 1, merchant="Boojum", category=6, recurring=True), history, NAMES)
    assert recurring == []


def test_category_spike_needs_two_months_of_history():
    eating = [txn(i, 20, 30 + i, category=6, merchant="Costa") for i in range(0, 50, 10)]  # Sep-Oct
    this_month = [txn(100 + i, 30, i, category=6, merchant="Costa") for i in range(6)]
    report = detect_anomalies(eating + this_month, category_names=NAMES, today=TODAY)
    spikes = [f for f in report.flags if f.type == "category_spike"]
    assert len(spikes) == 1 and spikes[0].category_name == "Eating Out"
    assert "November 2026" in spikes[0].message

    short = detect_anomalies(this_month, category_names=NAMES, today=TODAY)
    assert not [f for f in short.flags if f.type == "category_spike"]
    assert short.history_status in ("insufficient", "limited")


def _add(db, user, amount, days_ago, merchant="Tesco", name="Groceries"):
    t = Transaction(user_id=user.user_id, merchant_name=merchant, amount=amount,
                    transaction_date=TODAY - timedelta(days=days_ago), category_id=category_id(db, name))
    db.add(t)
    db.commit()
    return t


def test_alerts_stored_in_alerts_table_once(db):
    user = make_user(db)
    for i in range(8):
        _add(db, user, 40 + i, 60 - i * 5)
    big = _add(db, user, 200, 0)

    report = analyse_user(db, user.user_id, today=TODAY)
    created = store_alerts(db, user.user_id, report.flags)
    assert [a.alert_type for a in created] == ["large_transaction"]
    assert created[0].related_transaction_id == big.transaction_id
    assert created[0].is_read is False and "Unusually large" in created[0].message

    assert store_alerts(db, user.user_id, report.flags) == []  # no duplicates on re-analysis
    assert len(db.scalars(select(Alert)).all()) == 1


def test_user_isolation(db):
    me, other = make_user(db, "me@example.com"), make_user(db, "other@example.com")
    for i in range(8):
        _add(db, other, 40 + i, 60 - i * 5)
    _add(db, other, 300, 0)
    _add(db, me, 300, 0)  # my only transaction: not enough history to judge
    assert analyse_user(db, me.user_id, today=TODAY).flags == []
    theirs = analyse_user(db, other.user_id, today=TODAY).flags
    assert [f.type for f in theirs if f.type == "amount_outlier"] == ["amount_outlier"]
    assert all(f.amount == 300.0 for f in theirs)


def test_check_new_transaction_uses_only_earlier_history(db):
    user = make_user(db)
    for i in range(8):
        _add(db, user, 40 + i, 60 - i * 5)
    new = _add(db, user, 210, 0)
    flags = check_new_transaction(db, new)
    assert flags and flags[0].transaction_id == new.transaction_id


def test_evaluation_regression_guard():
    results = evaluate()
    assert results["clean_flag_rate"] < 0.05
    assert results["by_factor"][4.0]["precision"] >= 0.9
    assert results["by_factor"][4.0]["recall"] >= 0.8
    assert results["by_factor"][1.5]["recall"] <= 0.2  # normal variation should not alert
