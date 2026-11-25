"""Money parsing."""
import re
from decimal import Decimal, InvalidOperation
 
def parse_money(value):
    value = value.strip().replace("€", "").replace(" ", "")
    value = re.sub(r"^EUR", "", value, flags=re.I)
 
    if "," in value and "." in value:
        # Both present: whichever comes last is the decimal point,
        # the other one is a thousands separator.
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
 
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None

# ive made the currency as euro default, earlier i was extracting the currency from the string, but it was not used anywhere, so i removed it. 
