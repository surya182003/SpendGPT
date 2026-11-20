"""Shared constants and regex patterns."""
import re

# Euros are the default and only currency.
CURRENCY = "EUR"

CUR = r"(?:EUR|€)"
AMT = r"\d{1,6}[.,]\d{2}"
SIGNED_AMT = rf"-?{AMT}"

# A line that is ONLY a price, e.g. "0.99", "0.99 A", "EUR13.61", "-0.30".
# Group 1 is the amount.
MONEY_RE = re.compile(
    rf"^\s*(?:{CUR}\s*)?({SIGNED_AMT})(?:\s*{CUR})?(?:\s+[A-Z0-9])?\s*$",
    re.IGNORECASE,
)