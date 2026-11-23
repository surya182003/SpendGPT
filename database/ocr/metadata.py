"""Merchant, date and item-count extraction."""
import re
from datetime import datetime

DATE_RE = re.compile(
    r"\b(?:Date\s*:\s*)?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    re.IGNORECASE,
)

DATE_FORMATS = (
    "%d/%m/%y", "%d-%m-%y", "%d/%m/%Y", "%d-%m-%Y",
    "%m/%d/%y", "%m-%d-%y", "%m/%d/%Y", "%m-%d-%Y",
)

MERCHANT_HINTS = {
    "lidl": "Lidl",
    "tesco": "Tesco",
    "aldi": "Aldi",
    "supervalu": "SuperValu",
    "dunnes stores": "Dunnes Stores",
}

ITEM_COUNT_RE = re.compile(r"^(\d{1,3})\s+items?\b", re.IGNORECASE)


def extract_merchant(lines):
    text = "\n".join(lines).lower()

    for hint, merchant in MERCHANT_HINTS.items():
        if hint in text:
            return merchant

    return None


def extract_date(lines):
    """Extract a receipt date (ISO format), preferring an explicit Date label."""
    date_matches = []

    for line in lines:
        match = DATE_RE.search(line)

        if match:
            date_matches.append((line.lower().startswith("date"), match.group(1)))

    if not date_matches:
        return None

    date_matches.sort(key=lambda item: item[0], reverse=True)
    value = date_matches[0][1]

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def extract_item_count(lines):
    """The receipt's own unit count, e.g. "12 Items"."""
    for line in lines:
        match = ITEM_COUNT_RE.match(line)

        if match:
            return int(match.group(1))

    return None
