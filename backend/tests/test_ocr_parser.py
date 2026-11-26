"""Unit tests for the rule-based receipt parser in database/ocr.

These work on OCR *text*, so they don't need indra-ocr installed.
"""
import ast
from decimal import Decimal
from pathlib import Path

import pytest

from metadata import extract_date, extract_item_count, extract_merchant
from money import parse_money
from normalize import normalize_lines
from receipt_parser import parse_receipt_text
from totals import extract_total
from validation import validate_receipt

OCR_DIR = Path(__file__).resolve().parents[2] / "database" / "ocr"


def _load_samples():
    """Read LIDL / CODES / ALDI text from test_reciept.py without executing it."""
    tree = ast.parse((OCR_DIR / "test_reciept.py").read_text(encoding="utf-8"))
    samples = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            name = node.targets[0].id
            if name in {"LIDL", "CODES", "ALDI"}:
                samples[name] = node.value.value
    return samples


SAMPLES = _load_samples()


def item(line_total, quantity=1):
    return {"line_total": Decimal(str(line_total)), "quantity": quantity}


# ---------- money ----------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.50", Decimal("12.50")),
        ("12,50", Decimal("12.50")),
        ("€12,50", Decimal("12.50")),
        ("EUR 3.10", Decimal("3.10")),
        ("eur3.10", Decimal("3.10")),
        (" 0.99 ", Decimal("0.99")),
        ("-0.30", Decimal("-0.30")),
        ("5", Decimal("5.00")),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["1,234.56", "1.234,56"])
def test_parse_money_thousands_separator(raw):
    assert parse_money(raw) == Decimal("1234.56")


# ---------- normalize ----------

def test_normalize_drops_blank_lines_and_collapses_spaces():
    assert normalize_lines("  Milk    1.15  \n\n\r\nBread\t1.89") == ["Milk 1.15", "Bread 1.89"]


def test_normalize_replaces_cyrillic_lookalikes():
    # "ТОМАТО" below is written with Cyrillic letters
    assert normalize_lines("ТОМАТО KETCHUP") == ["TOMATO KETCHUP"]


@pytest.mark.parametrize("sep", ["x", "X", "@", "*", "×"])
def test_normalize_merges_split_quantity(sep):
    assert normalize_lines(f"3\n{sep}\n0.79") == ["3 x 0.79"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("T\no\nt\na 1", "TOTAL"),   # "1" misread for "l"
        ("T\nO\nT\nA\nL", "TOTAL"),
        ("SUB\nTOT\nAL", "SUBTOTAL"),
        ("G\n0\n0\nD\nS", "GOODS"),  # "0" misread for "O"
    ],
)
def test_normalize_repairs_fragmented_labels(raw, expected):
    assert normalize_lines(raw) == [expected]


def test_normalize_leaves_normal_short_lines_alone():
    assert normalize_lines("A\nB\nC") == ["A", "B", "C"]


# ---------- totals ----------

def test_total_line_beats_subtotal():
    lines = ["Subtotal 9.00", "Total 10.00"]
    assert extract_total(lines) == (Decimal("10.00"), "total")


def test_total_on_next_line():
    assert extract_total(["TOTAL", "18.83"]) == (Decimal("18.83"), "total")


@pytest.mark.parametrize("label", ["TOTAL SAVINGS", "TOTAL VAT"])
def test_total_ignores_lookalike_labels(label):
    assert extract_total([f"{label} 0.44"]) == (None, None)


def test_subtotal_used_only_when_nothing_better():
    assert extract_total(["Subtotal 9.00"]) == (Decimal("9.00"), "subtotal")


def test_total_smaller_than_biggest_item_is_rejected():
    lines = ["Total 1.00", "Card payment 5.00"]
    amount, source = extract_total(lines, items=[item("4.50")])
    assert (amount, source) == (Decimal("5.00"), "card_payment")


def test_total_matching_item_sum_wins():
    # "Goods" (70) loses to "Total" (100) alone, but gets +40 for matching the item sum.
    lines = ["Total 9.99", "Goods 6.00"]
    amount, source = extract_total(lines, items=[item("2.00"), item("4.00")])
    assert (amount, source) == (Decimal("6.00"), "goods")


def test_item_sum_bonus_does_not_beat_total_by_itself():
    # "Sale" (55 + 40 = 95) still loses to "Total" (100).
    lines = ["Total 9.99", "Sale 6.00"]
    amount, _ = extract_total(lines, items=[item("2.00"), item("4.00")])
    assert amount == Decimal("9.99")


def test_zero_total_ignored():
    assert extract_total(["Total 0.00"]) == (None, None)


def test_negative_total_is_not_read_as_positive():
    assert extract_total(["Total -3.00"]) == (None, None)


def test_lone_price_is_never_a_total():
    assert extract_total(["Milk", "1.15", "Bread", "1.89"]) == (None, None)


# ---------- metadata ----------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("LIDL Wilton", "Lidl"),
        ("Tesco Ireland", "Tesco"),
        ("aldi stores", "Aldi"),
        ("SuperValu Cork", "SuperValu"),
        ("Dunnes Stores", "Dunnes Stores"),
        ("Corner Shop", None),
    ],
)
def test_extract_merchant(text, expected):
    assert extract_merchant([text]) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Date: 03/10/26", "2026-10-03"),   # day first
        ("12-10-2026", "2026-10-12"),
        ("01/31/26", "2026-01-31"),        # only valid as month first
        ("No date here", None),
        ("99/99/99", None),
    ],
)
def test_extract_date(line, expected):
    assert extract_date([line]) == expected


def test_extract_date_prefers_labelled_date():
    assert extract_date(["Printed 01/01/25", "Date: 05/06/26"]) == "2026-06-05"


@pytest.mark.parametrize(("line", "expected"), [("12 Items", 12), ("1 item", 1), ("Items: 3", None)])
def test_extract_item_count(line, expected):
    assert extract_item_count([line]) == expected


# ---------- validation ----------

def make_result(total, line_totals, item_count=None, total_source="total"):
    return {
        "total_amount": total,
        "total_source": total_source,
        "item_count": item_count,
        "items": [{"line_total": t, "quantity": 1.0} for t in line_totals],
    }


def test_valid_receipt_needs_no_review():
    result = validate_receipt(make_result(3.00, [1.00, 2.00]))
    assert result["validation_issues"] == []
    assert result["requires_review"] is False


@pytest.mark.parametrize(("total", "flagged"), [(3.02, False), (3.03, True), (2.98, False), (2.97, True)])
def test_item_sum_tolerance_is_two_cents(total, flagged):
    result = validate_receipt(make_result(total, [1.00, 2.00]))
    assert result["requires_review"] is flagged


def test_missing_total_flagged():
    assert "Receipt total could not be identified." in validate_receipt(make_result(None, [1.0]))["validation_issues"]


def test_no_items_flagged():
    assert "No line items were extracted." in validate_receipt(make_result(1.0, []))["validation_issues"]


def test_subtotal_source_flagged():
    issues = validate_receipt(make_result(3.0, [1.0, 2.0], total_source="subtotal"))["validation_issues"]
    assert "Total was taken from a subtotal line." in issues


def test_item_count_mismatch_flagged():
    issues = validate_receipt(make_result(3.0, [1.0, 2.0], item_count=5))["validation_issues"]
    assert any("says 5 items" in i for i in issues)


# ---------- full parser on real sample receipts ----------

@pytest.mark.parametrize(
    ("name", "total", "n_items", "merchant"),
    [("LIDL", 18.83, 15, "Lidl"), ("CODES", 6.79, 3, "Tesco"), ("ALDI", 13.61, 10, "Aldi")],
)
def test_sample_receipts_parse_cleanly(name, total, n_items, merchant):
    result = validate_receipt(parse_receipt_text(SAMPLES[name]))
    assert result["total_amount"] == total
    assert len(result["items"]) == n_items
    assert result["merchant_name"] == merchant
    assert result["requires_review"] is False, result["validation_issues"]


def test_sample_dates():
    assert parse_receipt_text(SAMPLES["LIDL"])["transaction_date"] == "2026-10-03"
    assert parse_receipt_text(SAMPLES["CODES"])["transaction_date"] == "2026-10-12"


def test_lidl_discounts_applied_to_previous_item():
    result = parse_receipt_text(SAMPLES["LIDL"])
    peanuts = next(i for i in result["items"] if i["item_name"] == "Dry Roasted Peanuts")
    assert peanuts["discount"] == 0.10
    assert peanuts["line_total"] == 1.99
    assert sorted(result["discounts"]) == [0.04, 0.10, 0.30]


def test_aldi_quantity_line_before_product():
    result = parse_receipt_text(SAMPLES["ALDI"])
    tuna = next(i for i in result["items"] if "TUNA" in i["item_name"])
    assert (tuna["quantity"], tuna["unit_price"], tuna["line_total"]) == (3.0, 0.79, 2.37)
    assert result["item_count"] == 12


def test_codes_receipt_strips_product_codes():
    names = [i["item_name"] for i in parse_receipt_text(SAMPLES["CODES"])["items"]]
    assert names == ["Brown Bread", "Cheese Slices", "Apples"]


def test_receipt_without_total_needs_review():
    result = validate_receipt(parse_receipt_text("Milk\n1.15 A\nBread\n1.89 A\n"))
    assert result["total_amount"] is None
    assert result["requires_review"] is True


def test_parser_keeps_raw_text():
    assert parse_receipt_text("Milk\n1.15")["raw_ocr_text"] == "Milk\n1.15"


def test_empty_text_does_not_crash():
    result = validate_receipt(parse_receipt_text(""))
    assert result["items"] == [] and result["total_amount"] is None
