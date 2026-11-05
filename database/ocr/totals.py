"""Receipt total extraction."""
import re
from decimal import Decimal

from money import parse_money
from patterns import CUR, MONEY_RE, SIGNED_AMT

# (priority, source name, label regex). Labels must match the WHOLE label
# part of the line, so "TOTAL SAVINGS" or "TOTAL VAT" never match "total".
TOTAL_RULES = [
    (100, "total", r"(?:grand\s+)?total(?:\s+(?:due|to\s+pay|payable|amount))?"),
    (90, "amount_due", r"(?:amount|balance)\s+due|total\s+to\s+pay|to\s+pay"),
    (70, "goods", r"goods"),
    (60, "card_payment",
     r"(?:credit|debit)?\s*card\s+sales?|card\s+payment|credit\s+card|debit\s+card"),
    (55, "sale", r"sales?"),
    (30, "subtotal", r"sub\s*-?total"),
]

WEAK_TOTAL_SOURCES = {"subtotal"}


def _labelled_amount(lines, index, label):
    """
    Amount for a labelled line, either on the same line
    ("Total: EUR13.61", "Card Sales EUR 13.61") or on the next line
    ("TOTAL" / "18.83").
    """
    line = lines[index]

    same_line = re.fullmatch(
        rf"(?:{label})\s*[:\-]?\s*(?:{CUR}\s*)?(?P<a>{SIGNED_AMT})(?:\s*{CUR})?",
        line,
        re.IGNORECASE,
    )

    if same_line:
        return parse_money(same_line.group("a"))

    label_only = re.fullmatch(rf"(?:{label})\s*[:\-]?", line, re.IGNORECASE)

    if label_only and index + 1 < len(lines):
        nxt = MONEY_RE.match(lines[index + 1])

        if nxt:
            return parse_money(nxt.group(1))

    return None


def collect_total_candidates(lines):
    candidates = []

    for index, line in enumerate(lines):
        for priority, source, label in TOTAL_RULES:
            amount = _labelled_amount(lines, index, label)

            if amount is not None:
                candidates.append({
                    "priority": priority,
                    "source": source,
                    "amount": amount,
                    "index": index,
                })
                break

    return candidates


def extract_total(lines, items=None):
    candidates = [
        c for c in collect_total_candidates(lines) if c["amount"] > 0
    ]

    if items:
        max_item = max(item["line_total"] for item in items)
        item_sum = sum((item["line_total"] for item in items), Decimal("0"))
        candidates = [
            c for c in candidates if c["amount"] >= max_item - Decimal("0.01")
        ]
    else:
        item_sum = None

    if not candidates:
        return None, None

    def score(candidate):
        value = candidate["priority"]

        agreeing = sum(
            1 for other in candidates
            if other is not candidate and other["amount"] == candidate["amount"]
        )
        value += 15 * agreeing

        if item_sum is not None and abs(candidate["amount"] - item_sum) <= Decimal("0.02"):
            value += 40

        return value

    best = max(candidates, key=score)
    return best["amount"], best["source"]
