import os
import certifi
import mysql.connector
from dotenv import load_dotenv
from pathlib import Path
import contextlib
import io
import json
import sys
import traceback
from datetime import date

# Load environment variables for DB connection
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Directory containing this script: database/ocr/
OCR_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OCR_DIR))

# my parser for receipts, which uses Indra OCR to extract text from images - change this to your own parser if you want to use a different OCR engine
from receipt_parser import parse_receipt_text
from receipt_parser import parse_receipt_text
from validation import validate_receipt

DEFAULT_IMAGE = OCR_DIR / "test_images" / "aldi_test.jpeg" # change to pick the image from frontend and backend, or from a test image in the test_images folder. This is just a default for testing purposes.

# ive added manual entry for user_id to avoid having to pass it as a command line argument. Change this to any valid user_id in your database.
# very important: make sure this user_id exists in your database, otherwise the insert will fail.
# also when using for backed update the logic to get the user_id from the backend instead of hardcoding it here.
MANUAL_USER_ID = 1  # Change this to any valid user_id in your database


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("TIDB_HOST"),
        port=int(os.getenv("TIDB_PORT", 4000)),
        user=os.getenv("TIDB_USER", ""),
        password=os.getenv("TIDB_PASSWORD", ""),
        database=os.getenv("TIDB_DATABASE", "student_spend_db"),
        ssl_ca=certifi.where(),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
    )


def run_indra_ocr(image_path):
    """Run Indra OCR on an image and return the recognised text as a string."""
    from indra_ocr.cli import main as indra_main

    old_argv = sys.argv
    sys.argv = ["indra-ocr", str(image_path), "--format", "text"]

    buffer = io.StringIO()

    try:
        # The CLI prints its result to stdout, so capture it.
        with contextlib.redirect_stdout(buffer):
            indra_main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise RuntimeError(f"Indra OCR exited with code {exc.code}")
    finally:
        sys.argv = old_argv

    return buffer.getvalue()


def process_receipt(image_path):
    image_path = Path(image_path)

    if not image_path.is_file():
        raise FileNotFoundError(f"Receipt image not found: {image_path}")

    raw_text = run_indra_ocr(image_path)

    if not raw_text.strip():
        raise RuntimeError("Indra OCR returned no text.")

    result = parse_receipt_text(raw_text)
    return validate_receipt(result)


def save_receipt_to_db(parsed_result, user_id):
    """Inserts the parsed receipt into transactions and receipt_items tables."""
    print(f"\nSaving receipt to TiDB for user_id = {user_id}...")
    
    conn = get_connection()
    cur = conn.cursor()

    try:
        # 1. Default category to 'Groceries' for supermarket receipts
        cur.execute("SELECT category_id FROM categories WHERE category_name = 'Groceries'")
        cat_row = cur.fetchone()
        category_id = cat_row[0] if cat_row else 1

        # Extract fields from parsed result (adjust keys based on your parser output)
        merchant = parsed_result.get("merchant_name", "Unknown Store")
        total_amount = parsed_result.get("total_amount", 0.0)
        txn_date = parsed_result.get("transaction_date") or date.today().isoformat() # my bad was earlier using just date which was not really fetting transaction date from the receipt, so changed it to get the transaction date from the parsed result, if not present then use today's date.
        receipt_hash = parsed_result.get("receipt_hash", "ocr_manual_hash")
        items = parsed_result.get("items", [])

        # 2. Insert main transaction
        txn_sql = """
            INSERT INTO transactions 
            (user_id, category_id, amount, merchant_name, transaction_date, is_recurring, receipt_hash, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """
        cur.execute(txn_sql, (
            user_id, 
            category_id, 
            total_amount, 
            merchant, 
            txn_date, 
            False, 
            receipt_hash
        ))
        
        transaction_id = cur.lastrowid

        # 3. Insert individual receipt line items
        if items:
            item_rows = []
            for item in items:
                name = item.get("item_name", "Unknown Item")
                norm = item.get("normalized_name", name.lower())
                qty = item.get("quantity", 1)
                unit_price = item.get("unit_price", 0.0)
                item_rows.append((transaction_id, name, norm, qty, unit_price))

            item_sql = """
                INSERT INTO receipt_items 
                (transaction_id, item_name, normalized_name, quantity, unit_price)
                VALUES (%s, %s, %s, %s, %s)
            """
            cur.executemany(item_sql, item_rows)

        conn.commit()
        print(f"Success! Inserted transaction ID {transaction_id} with {len(items)} items.")

    except Exception as e:
        conn.rollback()
        print(f" Failed to save receipt to database: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE

    print("Python:", sys.executable)
    print("Image:", image_path)

    try:
        result = process_receipt(image_path)
    except Exception:
        print("\nReceipt processing failed:")
        traceback.print_exc()
        return

    print("\n--- RAW OCR TEXT ---\n")
    print(result["raw_ocr_text"])

    print("\n--- PARSED RECEIPT ---\n")
    print(json.dumps(result, indent=2, default=str))

    # Save to database using the manual user_id
    try:
        save_receipt_to_db(result, MANUAL_USER_ID)
    except Exception:
        print("\nDatabase insertion failed.")


if __name__ == "__main__":
    main()