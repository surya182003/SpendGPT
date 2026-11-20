"""
-- References and Acknowledgements -- (added as suggested by professor)

The implementation of the rule-based receipt parsing component was informed by the open-source project [Spesa](https://github.com/humanitiesNerd/spesa). 
Its approach to deterministic receipt parsing, particularly the extraction of product descriptions, quantities, unit prices, totals (might have missed a few other things too),
was useful as a reference when designing the line-item extraction logic for SpendGPT. 
The SpendGPT implementation was developed and adapted to its own requirements and receipt formats.

"""

"""Line-item extraction (product section only)."""
import re
from decimal import Decimal

from money import parse_money
from patterns import AMT, CUR, MONEY_RE, SIGNED_AMT

NON_ITEM_LABELS = {
    "total", "subtotal", "grand total", "total savings", "savings",
    "credit card", "debit mastercard", "cash", "change", "sale",
    "approved", "contactless", "customer copy", "vat", "tax", "eur",
}

# The first of these marks the end of the product section.
END_RE = re.compile(
    r"^(?:sub\s*-?total|grand\s+total|total|goods|card\s+sales?|"
    r"(?:credit|debit)\s+card|amount\s+due|balance\s+due|payment|"
    r"cash|change|eft|visa|mastercard|\d{1,3}\s+items?)\b",
    re.IGNORECASE,
)

# Header/column lines that sit just before the first product : the header lines I have seen are "EUR", "Euro", "Description", "Item", "Items", "Qty", "Quantity", "Price" and "Amount"
#add any more header lines you have seen to this regex if you have seen any other header lines in receipts
START_RE = re.compile(
    r"^(?:eur|euro|description|item|items|qty|quantity|price|amount)$",
    re.IGNORECASE,
)

# Lines that are never products: card/terminal details, URLs, footers.
NOISE_RE = re.compile(
    r"(\*{3,}|\bwww\.|https?://|\S+@\S+\.\S+|"
    r"^(?:tid|mid|trn|trns|auth|rrn|aid|ref|tel|phone|fax|reg)\b|"
    r"^vat\s*(?:no|number|reg)|^\d{9,}$|^[\W_]+$|"
    r"customer\s+copy|merchant\s+copy|thank\s+you|please\s+retain|"
    r"verification|contactless)",
    re.IGNORECASE,
)

DISCOUNT_LABEL_RE = re.compile(
    r"\b(?:saving|savings|discount|offer\w*|lidl\s+plus|clubcard|"
    r"loyalty|coupon|promo\w*)",
    re.IGNORECASE,
)

CODE_ONLY_RE = re.compile(r"^\d{4,14}$")

# Product code followed by a description, which may itself start with a
# digit ("275578 6PK TOMATOES").
CODE_PREFIX_RE = re.compile(r"^(\d{4,14})\s+(.*[A-Za-z].*)$")

# "2 x 1.29" or "2 @ 1.29" on its own line, before the line total.
QTY_RE = re.compile(
    rf"^(?P<qty>\d+(?:[.,]\d+)?)\s*[x@*×]\s*(?:{CUR}\s*)?(?P<unit>{AMT})$",
    re.IGNORECASE,
)

# "Red Onions 0.99 A" / "5012345678900 Red Onions 0.99" on one line.
ITEM_LINE_RE = re.compile(
    rf"^(?:\d{{4,14}}\s+)?(?P<name>.*[A-Za-z].*?)\s+"
    rf"(?:{CUR}\s*)?(?P<price>{SIGNED_AMT})(?:\s*{CUR})?(?:\s+[A-Z])?$",
    re.IGNORECASE,
)


def find_item_section(lines):
    """
    Return (start, end) indexes of the product section.
    It ends at the first TOTAL / payment line and starts after the
    last header-like line (e.g. "EUR") above it.
    """
    end = len(lines)

    for index, line in enumerate(lines):
        if END_RE.match(line):
            end = index
            break

    start = 0

    for index in range(end):
        if START_RE.match(lines[index]):
            start = index + 1

    return start, end


def _is_valid_description(text):
    text = text.strip()

    return bool(
        len(re.findall(r"[A-Za-z]", text)) >= 3
        and not QTY_RE.match(text)
        and text.lower() not in NON_ITEM_LABELS
        and not MONEY_RE.match(text)
        and not CODE_ONLY_RE.match(text)
        and not NOISE_RE.search(text)
        and not END_RE.match(text)
        and not DISCOUNT_LABEL_RE.search(text)
    )


def _new_item(name, quantity, unit_price, gross):
    return {
        "item_name": name,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount": Decimal("0.00"),
        "gross": gross,
        "line_total": gross,
    }


def _record_discount(amount, discounts, last_item):
    """Store a negative amount as a discount and apply it to the last item."""
    discount = abs(amount)
    discounts.append(discount)

    if last_item is not None:
        last_item["discount"] += discount
        last_item["line_total"] = last_item["gross"] - last_item["discount"]


def _item_from_price_line(lines, index, start, amount):
    """Build an item from a price-only line and the lines above it."""
    j = index - 1
    quantity = Decimal("1.000")
    unit_price = amount

    qty_match = QTY_RE.match(lines[j]) if j >= start else None

    if qty_match:
        quantity = Decimal(qty_match.group("qty").replace(",", "."))
        unit_price = parse_money(qty_match.group("unit"))
        j -= 1

    had_code_line = False

    if j >= start and CODE_ONLY_RE.match(lines[j]):
        had_code_line = True
        j -= 1

    description = lines[j].strip() if j >= start else ""

    if not had_code_line:
        prefix = CODE_PREFIX_RE.match(description)

        if prefix:
            description = prefix.group(2)
    if quantity == Decimal("1.000") and j - 1 >= start:
        before = QTY_RE.match(lines[j - 1])

        if before:
            q = Decimal(before.group("qty").replace(",", "."))
            u = parse_money(before.group("unit"))

            if u is not None and abs(q * u - amount) <= Decimal("0.01"):
                quantity, unit_price = q, u

    if not _is_valid_description(description):
        return None

    return _new_item(description, quantity, unit_price, amount)


def extract_items(lines):
    start, end = find_item_section(lines)

    items = []
    discounts = []
    last_item = None

    for index in range(start, end):
        line = lines[index]

        if NOISE_RE.search(line) or QTY_RE.match(line):
            continue

        money = MONEY_RE.match(line)

        if money:
            amount = parse_money(money.group(1))

            if amount is None:
                continue

            if amount < 0:
                _record_discount(amount, discounts, last_item)
                continue

            item = _item_from_price_line(lines, index, start, amount)

            if item:
                items.append(item)
                last_item = item

            continue

        if DISCOUNT_LABEL_RE.search(line):
            continue
        next_is_price = index + 1 < end and MONEY_RE.match(lines[index + 1])
        single = None if next_is_price else ITEM_LINE_RE.match(line)

        if single and _is_valid_description(single.group("name")):
            amount = parse_money(single.group("price"))

            if amount is None:
                continue

            if amount < 0:
                _record_discount(amount, discounts, last_item)
                continue

            item = _new_item(
                single.group("name").strip(),
                Decimal("1.000"),
                amount,
                amount,
            )
            items.append(item)
            last_item = item

    return items, discounts