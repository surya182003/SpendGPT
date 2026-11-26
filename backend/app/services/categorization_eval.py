"""Evaluate the transaction categoriser on the team's seed dataset.

    cd backend
    python -m app.services.categorization_eval

Reported experiments:
  1. Majority-class baseline.
  2. ML only, stratified 5-fold CV on merchant names: merchants the model has seen.
  3. ML only, leave-merchant-out (GroupKFold): merchants never seen in training.
     This is the honest generalisation number. Seed data has only ~30 merchants.
  4. Rules only, on the clean seed merchants. Optimistic: the rules list
     includes these merchants by design.
  5. Hybrid pipeline (rules -> ML) on OCR-style noisy variants of the merchant
     names (upper-casing, store numbers/locations, dropped characters), with a
     fixed random seed so the run is reproducible. Some of these suffixes are
     stripped by preprocessing, so a second set uses suffixes that are not.
"""
import random
from collections import Counter

from app.services.categorization_service import (
    ML_MIN_PROBABILITY,
    MODEL_VERSION,
    CategoryModel,
    load_seed_training_data,
    match_rules,
)

SUFFIXES = ["", " 3021", " DUBLIN 2", " IE", " LTD", " *TRIP", " GALWAY", " #114", " STORES", " EXPRESS"]
# Suffixes the preprocessing does NOT strip, so the model has to cope with them.
UNSTRIPPED_SUFFIXES = [" BALLSBRIDGE", " POS", " CARD PAYMENT", " SWORDS", " CONTACTLESS", " RATHMINES"]


def _metrics(y_true: list[str], y_pred: list[str]) -> dict:
    from sklearn.metrics import accuracy_score, f1_score

    return {
        "n": len(y_true),
        "accuracy": round(accuracy_score(y_true, y_pred), 3),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 3),
    }


def noisy_variant(merchant: str, rng: random.Random, suffixes: list[str] = SUFFIXES) -> str:
    text = merchant.upper() if rng.random() < 0.6 else merchant
    if len(text) > 6 and rng.random() < 0.35:  # OCR drops a character
        i = rng.randrange(1, len(text) - 1)
        text = text[:i] + text[i + 1:]
    return text + rng.choice(suffixes)


def hybrid_predict(model: CategoryModel, text: str) -> tuple[str, str]:
    hit = match_rules(text)
    if hit:
        return hit[0], "rule"
    prediction = model.predict(text)
    if prediction and prediction[1] >= ML_MIN_PROBABILITY:
        return prediction[0], "ml"
    return "Other", "default"


def evaluate(seed: int = 42) -> dict:
    from sklearn.model_selection import GroupKFold, StratifiedKFold

    merchants, labels = load_seed_training_data(include_items=False)
    item_texts, item_labels = load_seed_training_data(include_items=True)
    item_texts, item_labels = item_texts[len(merchants):], item_labels[len(merchants):]
    results = {"model_version": MODEL_VERSION, "samples": len(merchants),
               "distinct_merchants": len(set(merchants)), "class_counts": dict(Counter(labels))}

    majority = Counter(labels).most_common(1)[0][0]
    results["baseline_majority"] = _metrics(labels, [majority] * len(labels))

    def cross_validate(splitter, groups=None) -> dict:
        y_true, y_pred = [], []
        for train_idx, test_idx in splitter.split(merchants, labels, groups):
            model = CategoryModel()
            model.train([merchants[i] for i in train_idx] + item_texts,
                        [labels[i] for i in train_idx] + item_labels)
            for i in test_idx:
                y_true.append(labels[i])
                y_pred.append(model.predict(merchants[i])[0])
        return _metrics(y_true, y_pred)

    results["ml_seen_merchants_5fold"] = cross_validate(StratifiedKFold(5, shuffle=True, random_state=seed))
    results["ml_unseen_merchants_groupkfold"] = cross_validate(GroupKFold(5), groups=merchants)

    rule_hits = [(match_rules(m), l) for m, l in zip(merchants, labels)]
    covered = [(hit[0], l) for hit, l in rule_hits if hit]
    results["rules_clean_seed"] = {
        "coverage": round(len(covered) / len(merchants), 3),
        **_metrics([l for _, l in covered], [p for p, _ in covered]),
    }

    rng = random.Random(seed)
    model = CategoryModel()
    model.train(merchants + item_texts, labels + item_labels)
    variants = [(noisy_variant(m, rng), l) for m, l in zip(merchants, labels)]
    predictions = [hybrid_predict(model, text) for text, _ in variants]
    results["hybrid_noisy_variants"] = {
        **_metrics([l for _, l in variants], [p for p, _ in predictions]),
        "decided_by": dict(Counter(source for _, source in predictions)),
        "examples": [f"{t!r} -> {p} ({s})" for (t, _), (p, s) in list(zip(variants, predictions))[:8]],
    }
    ml_only = [model.predict(text)[0] for text, _ in variants]
    results["ml_only_noisy_variants"] = _metrics([l for _, l in variants], ml_only)

    hard = [(noisy_variant(m, rng, UNSTRIPPED_SUFFIXES), l) for m, l in zip(merchants, labels)]
    hard_predictions = [hybrid_predict(model, text) for text, _ in hard]
    results["hybrid_noisy_unstripped_suffixes"] = {
        **_metrics([l for _, l in hard], [p for p, _ in hard_predictions]),
        "decided_by": dict(Counter(source for _, source in hard_predictions)),
    }
    return results


def main() -> None:
    results = evaluate()
    print(f"Category model {results['model_version']}: {results['samples']} labelled transactions, "
          f"{results['distinct_merchants']} distinct merchants")
    print("Class counts:", results["class_counts"])
    for key in ("baseline_majority", "ml_seen_merchants_5fold", "ml_unseen_merchants_groupkfold",
                "rules_clean_seed", "ml_only_noisy_variants", "hybrid_noisy_variants",
                "hybrid_noisy_unstripped_suffixes"):
        values = {k: v for k, v in results[key].items() if k != "examples"}
        print(f"  {key:32s} {values}")
    print("Noisy-variant examples:")
    for line in results["hybrid_noisy_variants"]["examples"]:
        print("   ", line)


if __name__ == "__main__":
    main()
