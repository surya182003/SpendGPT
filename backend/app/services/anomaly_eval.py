"""Evaluate unusual-spending detection on the team's seed transactions.

    cd backend
    python -m app.services.anomaly_eval

1. Clean data: how many seed transactions get flagged (a false-alarm proxy), and
   how the flags compare with the large_transaction alerts already in
   database/alerts.csv.
2. Injection: copies of the seed data where selected non-recurring transactions
   are set to `factor` x that user's median amount in the category. Measured
   against the median rather than the original amount, because tripling a small
   top-up shop can still be a perfectly normal grocery bill. Precision and
   recall of amount_outlier flags on the injected rows, per factor. Fixed
   random seed, so runs are reproducible.
"""
import csv
import random
from collections import defaultdict
from datetime import date
from statistics import median
from pathlib import Path
from types import SimpleNamespace

from app.services.anomaly_service import detect_anomalies

SEED_DIR = Path(__file__).resolve().parents[3] / "database"
FACTORS = [1.5, 2.0, 3.0, 4.0, 6.0]
INJECT_PER_USER = 6


def _read(name: str) -> list[dict]:
    with (SEED_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_seed_transactions() -> dict[int, list[SimpleNamespace]]:
    by_user = defaultdict(list)
    for row in _read("transactions.csv"):
        by_user[int(row["user_id"])].append(SimpleNamespace(
            transaction_id=int(row["transaction_id"]),
            user_id=int(row["user_id"]),
            category_id=int(float(row["category_id"])) if row["category_id"] else None,
            amount=float(row["amount"]),
            merchant_name=row["merchant_name"],
            transaction_date=date.fromisoformat(row["transaction_date"]),
            is_recurring=row["is_recurring"].strip().lower() == "true",
        ))
    return by_user


def _names() -> dict[int, str]:
    return {int(r["category_id"]): r["category_name"] for r in _read("categories.csv")}


def _outliers(transactions, names, today) -> set[int]:
    report = detect_anomalies(transactions, category_names=names, today=today, lookback_days=10_000)
    return {f.transaction_id for f in report.flags if f.type == "amount_outlier"}


def evaluate(seed: int = 7) -> dict:
    users, names = load_seed_transactions(), _names()
    today = max(t.transaction_date for txns in users.values() for t in txns)
    total = sum(len(txns) for txns in users.values())

    clean_flags = {uid: _outliers(txns, names, today) for uid, txns in users.items()}
    flagged = set().union(*clean_flags.values())
    seeded_large = {int(r["related_transaction_id"]) for r in _read("alerts.csv")
                    if r["alert_type"] == "large_transaction" and r["related_transaction_id"]}
    results = {
        "transactions": total,
        "clean_flag_rate": round(len(flagged) / total, 4),
        "clean_flags": len(flagged),
        "seeded_large_transaction_alerts": len(seeded_large),
        "agreement_with_seeded_alerts": len(flagged & seeded_large),
        "by_factor": {},
    }

    rng = random.Random(seed)
    for factor in FACTORS:
        tp = fp = fn = 0
        for uid, txns in users.items():
            candidates = [t for t in txns if not t.is_recurring and t.transaction_date.month >= 8]
            chosen = {t.transaction_id for t in rng.sample(candidates, min(INJECT_PER_USER, len(candidates)))}
            medians = {c: median(t.amount for t in txns if t.category_id == c)
                       for c in {t.category_id for t in txns}}
            injected = [SimpleNamespace(**{**vars(t), "amount": round(medians[t.category_id] * factor, 2)})
                        if t.transaction_id in chosen else t for t in txns]
            found = _outliers(injected, names, today) - clean_flags[uid]
            tp += len(found & chosen)
            fp += len(found - chosen)
            fn += len(chosen - found)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        results["by_factor"][factor] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
            "injected": tp + fn,
        }
    return results


def main() -> None:
    r = evaluate()
    print(f"{r['transactions']} seed transactions")
    print(f"Clean data: {r['clean_flags']} flagged as unusually large ({r['clean_flag_rate']:.1%})")
    print(f"Seeded large_transaction alerts: {r['seeded_large_transaction_alerts']}, "
          f"also flagged by this detector: {r['agreement_with_seeded_alerts']}")
    print("Injected over-spends (amount_outlier):")
    for factor, m in r["by_factor"].items():
        print(f"  x{factor:<4} precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f} "
              f"(n={m['injected']})")


if __name__ == "__main__":
    main()
