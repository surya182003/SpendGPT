from items import extract_items
from metadata import extract_date, extract_item_count, extract_merchant
from normalize import normalize_lines
from totals import extract_total


def _item_to_json(item):
    return {
        "item_name": item["item_name"],
        "quantity": float(item["quantity"]),
        "unit_price": float(item["unit_price"]),
        "discount": float(item["discount"]),
        "line_total": float(item["line_total"]),
    }


def parse_receipt_text(raw_text):
    lines = normalize_lines(raw_text)

    items, discounts = extract_items(lines)
    total, total_source = extract_total(lines, items)

    return {
        "merchant_name": extract_merchant(lines),
        "transaction_date": extract_date(lines),
        "total_amount": float(total) if total is not None else None,
        "total_source": total_source,
        "item_count": extract_item_count(lines),
        "items": [_item_to_json(item) for item in items],
        "discounts": [float(value) for value in discounts],
        "raw_ocr_text": raw_text,
    }
