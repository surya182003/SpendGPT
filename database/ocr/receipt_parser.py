import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

# --------------------------------------------------------------------------
# Shared patterns
# --------------------------------------------------------------------------

CUR = r"(?:EUR|€)"
AMT = r"\d{1,6}[.,]\d{2}"
SIGNED_AMT = rf"-?{AMT}"

# A line that is ONLY a price, e.g. "0.99", "0.99 A", "EUR13.61", "-0.30".
MONEY_RE = re.compile(
    rf"^\s*(?:{CUR}\s*)?({SIGNED_AMT})(?:\s*{CUR})?(?:\s+([A-Z0-9]))?\s*$",
    re.IGNORECASE,
)

# OCR sometimes returns Cyrillic look-alikes inside Latin words
# (e.g. "TOMATO" written with Cyrillic letters). Map them back to Latin.
_CYRILLIC = (
    "АВЕКМНОРСТХІ"
    "аеорсхуі"
)
_LATIN = "ABEKMHOPCTXIaeopcxyi"
HOMOGLYPHS = str.maketrans(_CYRILLIC, _LATIN)

DATE_RE = re.compile(
    r"\b(?:Date\s*:\s*)?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    re.IGNORECASE,
)

MERCHANT_HINTS = {
    "lidl": "Lidl",
    "tesco": "Tesco",
    "aldi": "Aldi",
    "supervalu": "SuperValu",
    "dunnes stores": "Dunnes Stores",
}

# --------------------------------------------------------------------------
# Total extraction
# --------------------------------------------------------------------------

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


def parse_money(value):
    """Convert a monetary string into Decimal."""
    value = value.strip().replace("€", "").replace(" ", "")
    value = re.sub(r"^EUR", "", value, flags=re.I)

    if "," in value and "." not in value:
        value = value.replace(",", ".")

    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _labelled_amount(lines, index, label):
    """
    Amount for a labelled line, either on the same line
    ("Total: EUR13.61", "Goods: 13.61", "Card Sales EUR 13.61")
    or on the next line ("TOTAL" / "18.83").
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
    """
    Pick the most trustworthy total.

    Safeguards:
    - only explicit labels count; a bare price is never a total
    - a total cannot be smaller than the most expensive single item
    - candidates are boosted when they agree with each other
      (e.g. TOTAL and the card payment line) or with the item sum

    Returns (amount, source) or (None, None).
    """
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


# --------------------------------------------------------------------------
# Item extraction (product section only)
# --------------------------------------------------------------------------

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

# "12 Items" - the receipt's own count of purchased units.
ITEM_COUNT_RE = re.compile(r"^(\d{1,3})\s+items?\b", re.IGNORECASE)

# Header/column lines that sit just before the first product.
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
# Code followed by a description, which may itself start with a digit
# ("275578 6PK TOMATOES"). this is product code followed by a description, which may itself start with a digit
CODE_PREFIX_RE = re.compile(r"^(\d{4,14})\s+(.*[A-Za-z].*)$")

# "2 x 1.29" or "2 @ 1.29" on its own line, before the line total.
QTY_RE = re.compile(
    rf"^(?P<qty>\d+(?:[.,]\d+)?)\s*[x@*×]\s*(?:{CUR}\s*)?(?P<unit>{AMT})$",
    re.IGNORECASE,
)

# "Red Onions 0.99 A" / "5012345678900 Red Onions 0.99" on one line.
ITEM_LINE_RE = re.compile(
    rf"^(?:(?P<code>\d{{4,14}})\s+)?(?P<name>.*[A-Za-z].*?)\s+"
    rf"(?:{CUR}\s*)?(?P<price>{SIGNED_AMT})(?:\s*{CUR})?(?:\s+(?P<tax>[A-Z]))?$",
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


def _new_item(name, code, quantity, unit_price, gross):
    return {
        "item_name": name,
        "product_code": code,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount": Decimal("0.00"),
        "gross": gross,
        "line_total": gross,
    }


def _apply_discount(item, discount):
    item["discount"] += discount
    item["line_total"] = item["gross"] - item["discount"]


def extract_items(lines):
    """
    Extract purchased items from the product section only.

    Supported layouts:
      Description / price line        Red Onions / 0.99 A
      Description + price one line    Red Onions 0.99 A
      Code + description + price      5012345678900 Red Onions 0.99
      Code line next to description   5012345678900 / Red Onions / 0.99
      Quantity line                   Apples / 2 x 1.29 / 2.58
      Negative line after an item     -0.30  (discount for that item)

    Returns (items, discounts) with Decimal values.
    """
    start, end = find_item_section(lines)

    items = []
    discounts = []
    last_item = None

    for index in range(start, end):
        line = lines[index]

        if NOISE_RE.search(line):
            continue

        if QTY_RE.match(line):
            continue

        money = MONEY_RE.match(line)

        # ---- a price on its own line -------------------------------
        if money:
            amount = parse_money(money.group(1))

            if amount is None:
                continue

            if amount < 0:
                discounts.append(abs(amount))

                if last_item is not None:
                    _apply_discount(last_item, abs(amount))

                continue

            j = index - 1
            quantity = Decimal("1.000")
            unit_price = amount

            qty_match = QTY_RE.match(lines[j]) if j >= start else None

            if qty_match:
                quantity = Decimal(qty_match.group("qty").replace(",", "."))
                unit_price = parse_money(qty_match.group("unit"))
                j -= 1

            code = None

            if j >= start and CODE_ONLY_RE.match(lines[j]):
                code = lines[j]
                j -= 1

            description = lines[j].strip() if j >= start else ""

            prefix = CODE_PREFIX_RE.match(description)

            if prefix and code is None:
                code, description = prefix.group(1), prefix.group(2)

            # Some receipts (Aldi) put the quantity line BEFORE the product
            # line. Only accept it when quantity x unit price = line price,
            # so a neighbouring item's quantity line is never borrowed.
            if quantity == Decimal("1.000") and j - 1 >= start:
                before = QTY_RE.match(lines[j - 1])

                if before:
                    q = Decimal(before.group("qty").replace(",", "."))
                    u = parse_money(before.group("unit"))

                    if u is not None and abs(q * u - amount) <= Decimal("0.01"):
                        quantity, unit_price = q, u

            if _is_valid_description(description):
                item = _new_item(description, code, quantity, unit_price, amount)
                items.append(item)
                last_item = item

            continue

        if DISCOUNT_LABEL_RE.search(line):
            continue

        # ---- description and price on the same line ----------------
        # Skip when the next line is a price: then THIS line is only a
        # description that happens to end in a number
        # (e.g. "Natural Yogurt 1.52" / "0.65 A").
        next_is_price = (
            index + 1 < end and MONEY_RE.match(lines[index + 1])
        )

        single = None if next_is_price else ITEM_LINE_RE.match(line)

        if single and _is_valid_description(single.group("name")):
            amount = parse_money(single.group("price"))

            if amount is None:
                continue

            if amount < 0:
                discounts.append(abs(amount))

                if last_item is not None:
                    _apply_discount(last_item, abs(amount))

                continue

            item = _new_item(
                single.group("name").strip(),
                single.group("code"),
                Decimal("1.000"),
                amount,
                amount,
            )
            items.append(item)
            last_item = item

    return items, discounts


# --------------------------------------------------------------------------
# Everything else
# --------------------------------------------------------------------------

def _merge_split_quantities(lines):
    """Join a quantity line the OCR split into "3" / "X" / "0.79"."""
    merged = []
    i = 0

    while i < len(lines):
        if (
            i + 2 < len(lines)
            and re.fullmatch(r"\d{1,3}", lines[i])
            and re.fullmatch(r"[x@*×]", lines[i + 1], re.IGNORECASE)
            and re.fullmatch(AMT, lines[i + 2])
        ):
            merged.append(f"{lines[i]} x {lines[i + 2]}")
            i += 3
        else:
            merged.append(lines[i])
            i += 1

    return merged


def _fold(text):
    """Lower-case letters/digits only, with common OCR digit/letter swaps."""
    text = re.sub(r"[^a-z0-9]", "", text.lower())
    return text.replace("1", "l").replace("0", "o").replace("5", "s")


FRAGMENT_LABELS = {"total": "TOTAL", "subtotal": "SUBTOTAL", "goods": "GOODS"}


def _repair_fragmented_labels(lines):
    """
    OCR can split a label into one character per line:
        T / o / t / a 1   ->   TOTAL
    Only runs of very short lines that spell a known label are joined.
    """
    repaired = []
    i = 0

    while i < len(lines):
        replacement = None

        for size in range(3, 9):
            window = lines[i:i + size]

            if len(window) < size:
                break

            if not all(
                len(re.sub(r"\s", "", part)) <= 3 and not MONEY_RE.match(part)
                for part in window
            ):
                break

            label = FRAGMENT_LABELS.get(_fold("".join(window)))

            if label:
                replacement = (label, size)
                break

        if replacement:
            repaired.append(replacement[0])
            i += replacement[1]
        else:
            repaired.append(lines[i])
            i += 1

    return repaired


def normalize_lines(raw_text):
    """Clean OCR text while preserving its line order."""
    lines = []

    for line in raw_text.replace("\r", "\n").split("\n"):
        line = line.translate(HOMOGLYPHS)
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    lines = _merge_split_quantities(lines)
    lines = _repair_fragmented_labels(lines)

    return lines


def extract_item_count(lines):
    """The receipt's own unit count, e.g. "12 Items"."""
    for line in lines:
        match = ITEM_COUNT_RE.match(line)

        if match:
            return int(match.group(1))

    return None


def extract_merchant(lines):
    text = "\n".join(lines).lower()

    for hint, merchant in MERCHANT_HINTS.items():
        if hint in text:
            return merchant

    return None


def extract_date(lines):
    """Extract a receipt date, preferring an explicit Date label."""
    date_matches = []

    for line in lines:
        match = DATE_RE.search(line)

        if match:
            date_matches.append((line.lower().startswith("date"), match.group(1)))

    if not date_matches:
        return None

    date_matches.sort(key=lambda item: item[0], reverse=True)
    value = date_matches[0][1]

    for fmt in ("%d/%m/%y", "%d-%m-%y", "%d/%m/%Y", "%d-%m-%Y",
                "%m/%d/%y", "%m-%d-%y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def extract_currency(raw_text):
    if "€" in raw_text or re.search(r"\bEUR\b", raw_text, re.I):
        return "EUR"

    if "$" in raw_text or re.search(r"\bUSD\b", raw_text, re.I):
        return "USD"

    if "£" in raw_text or re.search(r"\bGBP\b", raw_text, re.I):
        return "GBP"

    return None


def extract_tax(lines):
    """
    Conservative: only an explicit TOTAL VAT / TOTAL TAX line.
    Per-rate VAT breakdowns are not summed because OCR scrambles them.
    """
    for index, line in enumerate(lines):
        if re.search(r"\b(?:TOTAL\s+VAT|VAT\s+TOTAL|TOTAL\s+TAX)\b", line, re.I):
            match = MONEY_RE.search(line)

            if match:
                return parse_money(match.group(1))

            if index + 1 < len(lines):
                match = MONEY_RE.match(lines[index + 1])

                if match:
                    return parse_money(match.group(1))

    return None


def validate_receipt(result):
    """Report inconsistencies without silently changing extracted data."""
    issues = []

    total = result.get("total_amount")
    items = result.get("items", [])

    if total is None:
        issues.append("Receipt total could not be identified.")

    if not items:
        issues.append("No line items were extracted.")

    if result.get("total_source") in WEAK_TOTAL_SOURCES:
        issues.append("Total was taken from a subtotal line.")

    if total is not None and items:
        item_sum = sum(
            (Decimal(str(item["line_total"])) for item in items),
            Decimal("0.00"),
        )
        difference = abs(Decimal(str(total)) - item_sum)

        if difference > Decimal("0.02"):
            issues.append(
                f"Item totals differ from receipt total by {difference:.2f} EUR."
            )

    item_count = result.get("item_count")

    if item_count is not None and items:
        units = sum(Decimal(str(item["quantity"])) for item in items)

        if units != Decimal(item_count):
            issues.append(
                f"Receipt says {item_count} items but {units:g} were extracted."
            )

    result["validation_issues"] = issues
    result["requires_review"] = bool(issues)

    return result


def _item_to_json(item):
    return {
        "item_name": item["item_name"],
        "product_code": item["product_code"],
        "quantity": float(item["quantity"]),
        "unit_price": float(item["unit_price"]),
        "discount": float(item["discount"]),
        "line_total": float(item["line_total"]),
    }


def parse_receipt_text(raw_text):
    lines = normalize_lines(raw_text)

    items, discounts = extract_items(lines)
    total, total_source = extract_total(lines, items)
    tax = extract_tax(lines)

    return {
        "merchant_name": extract_merchant(lines),
        "transaction_date": extract_date(lines),
        "total_amount": float(total) if total is not None else None,
        "total_source": total_source,
        "tax_amount": float(tax) if tax is not None else None,
        "item_count": extract_item_count(lines),
        "currency": extract_currency(raw_text),
        "items": [_item_to_json(item) for item in items],
        "discounts": [float(value) for value in discounts],
        "raw_ocr_text": raw_text,
    }

# the vat has been extracted from the receipt and is included in the result dictionary under the key "tax_amount". The value is a float representing the total VAT amount found on the receipt. If no VAT amount is found, this key will have a value of None.
# some receipts may not have a VAT amount, in which case the "tax_amount" key will be None.
# having trouble with the vat extraction, you can check the "raw_ocr_text" key in the result dictionary to see the original OCR text and verify if the VAT amount is present and correctly formatted.