"""Transaction categorisation: rules, ML, user history, LLM tier and category_id mapping."""
from datetime import date

import pytest

from app.models.category import Category
from app.models.transaction import Transaction
from app.services.categorization_eval import evaluate
from app.services.categorization_service import (
    categorize_receipt,
    categorize_transaction,
    get_category_model,
    match_rules,
    model_text,
    normalize_text,
)
from tests.conftest import FakeLMStudio, category_id, make_user


def test_normalize_text():
    assert normalize_text("McDonald's #123") == "mcdonalds 123"
    assert normalize_text("  Café  Nero ") == "cafe nero"
    assert normalize_text(None) == ""
    assert model_text("TESCO STORES 3021 DUBLIN 2") == "tesco"


@pytest.mark.parametrize("merchant, expected", [
    ("Tesco", "Groceries"), ("LIDL IRELAND GMBH", "Groceries"), ("Landlord - Rent", "Rent"),
    ("Electric Ireland", "Utilities"), ("Leap Card Top-up", "Transport"), ("Uber", "Transport"),
    ("Uber Eats", "Eating Out"), ("Supermac's", "Eating Out"), ("McCabes Pharmacy", "Health"),
    ("Penneys", "Shopping"), ("Amazon.ie", "Shopping"), ("Amazon Prime", "Subscriptions"),
    ("Cineworld", "Entertainment"), ("Spotify", "Subscriptions"), ("Gym Membership", "Subscriptions"),
])
def test_known_merchants_map_to_existing_category_ids(db, merchant, expected):
    result = categorize_transaction(db, merchant)
    assert result.category_name == expected
    assert result.category_id == category_id(db, expected)
    assert result.source == "rule"


def test_category_ids_come_from_the_live_table_not_hardcoded(db):
    # Renumber Groceries: the prediction must follow the database.
    groceries = db.get(Category, category_id(db, "Groceries"))
    db.delete(groceries)
    db.commit()
    db.add(Category(category_id=77, category_name="Groceries", spend_type="Essential"))
    db.commit()
    assert categorize_transaction(db, "Aldi").category_id == 77


def test_prediction_missing_from_table_is_never_invented(db):
    db.delete(db.get(Category, category_id(db, "Subscriptions")))
    db.commit()
    result = categorize_transaction(db, "Netflix")
    assert result.source == "default"
    assert result.category_name == "Other"
    assert "not in the categories table" in result.reason


def test_unknown_merchant_defaults_to_other_with_zero_confidence(db):
    result = categorize_transaction(db, "Xyzzy Holdings")
    assert (result.category_name, result.source, result.confidence) == ("Other", "default", 0.0)
    assert result.category_id == category_id(db, "Other")


@pytest.mark.parametrize("merchant", [None, "", "   ", "Unknown", "N/A"])
def test_missing_merchant_and_description(db, merchant):
    result = categorize_transaction(db, merchant, None)
    assert result.source == "default"
    assert "no merchant" in result.reason


def test_description_used_when_merchant_missing(db):
    result = categorize_transaction(db, None, "monthly Netflix plan")
    assert result.category_name == "Subscriptions"
    assert "description" in result.reason


def test_ml_handles_ocr_typos(db):
    result = categorize_transaction(db, "NETFLX")
    assert (result.category_name, result.source) == ("Subscriptions", "ml")
    assert 0.6 <= result.confidence <= 1.0


def test_model_trains_on_seed_dataset():
    model = get_category_model()
    assert model.trained and model.samples > 1000
    assert "Groceries" in model.classes


def test_user_history_wins_and_is_scoped_to_the_user(db):
    me, other = make_user(db, "me@example.com"), make_user(db, "other@example.com")
    db.add(Transaction(user_id=me.user_id, merchant_name="Corner Shop", amount=5,
                       transaction_date=date(2026, 11, 1), category_id=category_id(db, "Groceries")))
    db.commit()

    mine = categorize_transaction(db, "corner shop", user_id=me.user_id)
    assert (mine.category_name, mine.source) == ("Groceries", "history")
    theirs = categorize_transaction(db, "Corner Shop", user_id=other.user_id)
    assert theirs.source != "history"


def test_llm_tier_only_when_enabled_and_constrained_to_categories(db):
    llm = FakeLMStudio(json_reply={"category": "entertainment"})
    assert categorize_transaction(db, "Xyzzy Holdings", client=llm).source == "default"  # use_llm False
    assert llm.calls == []

    result = categorize_transaction(db, "Xyzzy Holdings", client=llm, use_llm=True)
    assert (result.category_name, result.source) == ("Entertainment", "llm")
    assert "Groceries" in llm.calls[0][0]["content"]  # prompt lists the real categories


def test_llm_off_list_answer_or_outage_falls_back(db):
    off_list = FakeLMStudio(json_reply={"category": "Crypto"})
    assert categorize_transaction(db, "Xyzzy", client=off_list, use_llm=True).source == "default"
    offline = FakeLMStudio(available=False)
    assert categorize_transaction(db, "Xyzzy", client=offline, use_llm=True).source == "default"


def test_receipt_uses_merchant_when_known(db):
    result = categorize_receipt(db, "ALDI STORES", [{"item_name": "HOODIE", "quantity": 1, "unit_price": 20}])
    assert result.category_name == "Groceries"


def test_receipt_with_unknown_merchant_uses_items(db):
    items = [
        {"item_name": "MILK 2L", "quantity": 1, "unit_price": 1.89},
        {"item_name": "WHITE SLICED BREAD", "quantity": 2, "unit_price": 1.2},
        {"item_name": "USB-C CABLE", "quantity": 1, "unit_price": 2.0},
    ]
    result = categorize_receipt(db, "Unknown", items)
    assert result.category_name == "Groceries"
    assert result.category_id == category_id(db, "Groceries")
    assert "merchant unknown" in result.reason


def test_receipt_with_nothing_recognisable(db):
    assert categorize_receipt(db, None, []).source == "default"


def test_rules_prefer_longer_keywords():
    assert match_rules("Tesco Mobile")[0] == "Utilities"
    assert match_rules("Tesco")[0] == "Groceries"


def test_evaluation_metrics_regression_guard():
    results = evaluate()
    assert results["ml_seen_merchants_5fold"]["accuracy"] >= 0.95
    assert results["hybrid_noisy_unstripped_suffixes"]["accuracy"] >= 0.95
    assert results["baseline_majority"]["accuracy"] < 0.5
