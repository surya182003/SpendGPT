"""Consistency checks on a parsed receipt."""
from decimal import Decimal

from patterns import CURRENCY
from totals import WEAK_TOTAL_SOURCES


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
                f"Item totals differ from receipt total by {difference:.2f} {CURRENCY}."
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
