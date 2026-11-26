import importlib.util
import sys
import traceback
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
OCR_PY = next((p for p in (HERE / "ocr" / "ocr.py", HERE / "ocr.py") if p.exists()), HERE / "ocr" / "ocr.py")
CENT = Decimal("0.01")


def load_ocr():
    if not OCR_PY.exists():
        raise SystemExit(f"Can't find ocr.py at {OCR_PY}")
    spec = importlib.util.spec_from_file_location("ocr_pipeline", OCR_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

#Turning a parsed number into a 2-decimal Decimal (None if it isn't a number).
def dec(value):
    try:
        return Decimal(str(value)).quantize(CENT)
    except (InvalidOperation, ValueError):
        return None

#comparing the data dump from ocr.py with the data read back from the database, to see if they match. Returns a list of (ok, text) tuples, where ok is True if the parsed and saved values match, and text is a human-readable description of what was compared.
def check_receipt(parsed, txn, rows):
    out = []

    def compare(label, parsed_value, saved_value, fmt=str):
        ok = parsed_value == saved_value
        text = f"{label}: {fmt(saved_value)}" if ok else \
            f"{label}: parsed {fmt(parsed_value)}, saved {fmt(saved_value)}"
        out.append((ok, text))

    compare("merchant", parsed.get("merchant_name"), txn["merchant_name"])
    compare("date", str(parsed.get("date"))[:10], str(txn["transaction_date"]))
    compare("total", dec(parsed.get("total_amount")), txn["amount"])

    items = parsed.get("items") or []
    compare("item count", len(items), len(rows))

    show = lambda t: f"{t[0]} / {t[1]} / x{t[2]} @ {t[3]}"  # name / normalized name / qty @ price
    for n, (item, row) in enumerate(zip(items, rows), 1):
        name = item.get("item_name")
        parsed_item = (name,
                       item.get("normalized_name", (name or "").lower()),  # same default ocr.py uses
                       dec(item.get("quantity", 1)),                       # same default ocr.py uses
                       dec(item.get("unit_price")))
        saved_item = (row["item_name"], row["normalized_name"], row["quantity"], row["unit_price"])
        compare(f"item {n}", parsed_item, saved_item, fmt=show)
    return out


def main():
    keep = "--keep" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    ocr = load_ocr()
    image = Path(args[0]) if args else Path(ocr.DEFAULT_IMAGE)
    user_id = ocr.MANUAL_USER_ID
    print(f"Image:   {image}\nUser ID: {user_id}\n")

    # 1. Run the real OCR + parser
    print("Running OCR and parser...")
    try:
        parsed = ocr.process_receipt(image)
    except Exception:
        print("\nFAILED: OCR/parsing crashed:")
        traceback.print_exc()
        return 1

    receipt_hash = parsed.get("receipt_hash", "ocr_manual_hash")  # same default ocr.py uses
    conn = ocr.get_connection()
    conn.autocommit = True  # always read the latest data, never an old snapshot
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT transaction_id FROM transactions WHERE user_id = %s", (user_id,))
        ids_before = {r["transaction_id"] for r in cur.fetchall()}

        # If the parser gives a receipt_hash, it must not be saved already (the save would be rejected as a duplicate)
        if receipt_hash is not None:
            cur.execute("SELECT transaction_id FROM transactions WHERE user_id = %s AND receipt_hash = %s",
                        (user_id, receipt_hash))
            if cur.fetchone():
                print(f"\nFAILED: user {user_id} already has a receipt with receipt_hash '{receipt_hash}', "
                      "so saving would be rejected as a duplicate.\n"
                      "Delete that row first (for example from an earlier ocr.py run), then run this again:\n"
                      f"  DELETE FROM transactions WHERE user_id = {user_id} AND receipt_hash = '{receipt_hash}';")
                return 1

        print("Saving with the pipeline's save_receipt_to_db()...")
        try:
            ocr.save_receipt_to_db(parsed, user_id)
        except Exception as e:
            print(f"\nFAILED: the pipeline could not save the receipt: {e}")
            return 1

        cur.execute("SELECT * FROM transactions WHERE user_id = %s", (user_id,))
        new_txns = [r for r in cur.fetchall() if r["transaction_id"] not in ids_before]
        if len(new_txns) != 1:
            print(f"\nFAILED: expected 1 new transaction for user {user_id}, found {len(new_txns)}.")
            return 1
        txn = new_txns[0]
        tid = txn["transaction_id"]

        try:
            cur.execute("SELECT * FROM receipt_items WHERE transaction_id = %s ORDER BY item_id", (tid,))
            rows = cur.fetchall()

            print(f"\nComparing parsed OCR data with the database (transaction #{tid}):")
            results = check_receipt(parsed, txn, rows)
            for ok, text in results:
                print(f"  {'PASS' if ok else 'FAIL'}  {text}")
        finally:
            if keep:
                print(f"\n(kept transaction #{tid} in the database)")
            else:
                cur.execute("DELETE FROM receipt_items WHERE transaction_id = %s", (tid,))
                cur.execute("DELETE FROM transactions WHERE transaction_id = %s", (tid,))
                conn.commit()
                print(f"\n(deleted test transaction #{tid})")
    finally:
        cur.close()
        conn.close()

    failed = [text for ok, text in results if not ok]
    if failed:
        print(f"\nFAILED - {len(failed)} mismatch(es)")
        return 1
    print("\nPASSED - everything the OCR parsed was saved correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())