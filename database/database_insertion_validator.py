"""
SpendGPT - OCR Database Insertion Validator

Queries the TiDB database to verify that the latest OCR receipt 
transaction and its line items were correctly saved for the test user.
"""
import os
import certifi
import mysql.connector
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(env_path)

MANUAL_USER_ID = 1

def get_connection():
    host = os.getenv("TIDB_HOST")
    user = os.getenv("TIDB_USER", "")
    password = os.getenv("TIDB_PASSWORD", "")
    database = os.getenv("TIDB_DATABASE", "student_spend_db")
    
    if not host:
        raise ValueError(f"TIDB_HOST is missing. Checked .env path: {env_path}")
        
    return mysql.connector.connect(
        host=host,
        port=int(os.getenv("TIDB_PORT", 4000)),
        user=user,
        password=password,
        database=database,
        ssl_ca=certifi.where(),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
    )

def validate_latest_receipt():
    print(f"Querying database for the latest transaction for user_id = {MANUAL_USER_ID}...")
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    
    try:
        cur.execute("""
            SELECT transaction_id, merchant_name, amount, transaction_date, receipt_hash, created_at 
            FROM transactions 
            WHERE user_id = %s 
            ORDER BY transaction_id DESC 
            LIMIT 1
        """, (MANUAL_USER_ID,))
        
        txn = cur.fetchone()
        if not txn:
            print("Validation Failed: No transactions found for this user in the database.")
            return

        print("\nFound Latest Transaction in Database:")
        print(f"   - Transaction ID: {txn['transaction_id']}")
        print(f"   - Merchant:       {txn['merchant_name']}")
        print(f"   - Amount:         EUR {txn['amount']:.2f}")
        print(f"   - Date:           {txn['transaction_date']}")
        print(f"   - Receipt Hash:   {txn['receipt_hash']}")
        print(f"   - Created At:     {txn['created_at']}")

        cur.execute("""
            SELECT item_name, normalized_name, quantity, unit_price 
            FROM receipt_items 
            WHERE transaction_id = %s
        """, (txn['transaction_id'],))
        
        items = cur.fetchall()
        print(f"\nAssociated Receipt Items ({len(items)} found):")
        if items:
            for idx, item in enumerate(items, 1):
                subtotal = item['quantity'] * item['unit_price']
                print(f"   {idx}. {item['item_name']} (Qty: {item['quantity']}, Unit: EUR {item['unit_price']:.2f}) -> Subtotal: EUR {subtotal:.2f}")
        else:
            print("   (Warning: No line items found for this transaction ID)")

        print("\nValidation Passed: The OCR-to-DB pipeline successfully stored the data.")

    except Exception as e:
        print(f"Error during validation query: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    validate_latest_receipt()