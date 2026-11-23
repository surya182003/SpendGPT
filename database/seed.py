import os
import certifi
import numpy as np
import pandas as pd
import mysql.connector
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
SEED_DOMAIN = "seed.spendgpt.dev"

def get_connection():
    user, password = os.getenv("TIDB_USER", ""), os.getenv("TIDB_PASSWORD", "")
    if not user or not password or user.startswith("PASTE_") or password.startswith("PASTE_"):
        raise SystemExit("Fill in TIDB_USER and TIDB_PASSWORD in the .env file first.")
    return mysql.connector.connect(
        host=os.getenv("TIDB_HOST"),
        port=int(os.getenv("TIDB_PORT", 4000)),
        user=user,
        password=password,
        database=os.getenv("TIDB_DATABASE", "student_spend_db"),
        ssl_ca=certifi.where(),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
    )

def reset_seed_data(cur):
# i think i already seeded some data in the database, so to be safe ive added this function to remove any previously seeded data before inserting new seed data. it will delete all users with emails ending in "@seed.spendgpt.dev" and all related data in other tables (accounts, budgets, transactions, receipt_items, alerts, predictions, reference_prices). this is to ensure that the seed data is consistent and doesn't conflict with any existing data.
    print("Resetting seed data...")
    print("Removing any previously seeded data...")
    like = f"%@{SEED_DOMAIN}"
    sub = "SELECT user_id FROM users WHERE email LIKE %s"
    
    tables_to_clean = [
        f"DELETE FROM alerts WHERE user_id IN ({sub})",
        f"DELETE FROM predictions WHERE user_id IN ({sub})",
        f"DELETE FROM receipt_items WHERE transaction_id IN (SELECT transaction_id FROM transactions WHERE user_id IN ({sub}))",
        f"DELETE FROM transactions WHERE user_id IN ({sub})",
        f"DELETE FROM budgets WHERE user_id IN ({sub})",
        f"DELETE FROM accounts WHERE user_id IN ({sub})",
    ]
    
    for stmt in tables_to_clean:
        cur.execute(stmt, (like,))
        
    cur.execute("DELETE FROM users WHERE email LIKE %s", (like,))
    cur.execute("DELETE FROM reference_prices WHERE source = 'seed'")

def insert_dataframe(cur, df, table_name):
#i previously had an issue with inserting data into the database where the date columns were not formatted correctly for MySQL. to fix this, ive added logic to detect date/time columns by their names (like 'date', 'created_at', 'observed_on') and convert them to the proper MySQL format (YYYY-MM-DD HH:MM:SS) before inserting. this should prevent any errors related to date formatting when seeding the database.
# the error occured because the csv files had dates in formats like DD-MM-YYYY or other variations, which MySQL does not accept directly. by using pandas to parse and reformat these dates, we ensure that the data is compatible with the database schema.
# i manually inputted the dates, hence the problem with formating. this function now handles that by checking column names and applying the correct formatting.
    if df.empty:
        return 0

    # Fix timestamp/date formatting for MySQL (YYYY-MM-DD HH:MM:SS)
    for col in df.columns:
        # Detect date/time columns by naming convention
        if any(keyword in col.lower() for keyword in ['date', 'created_at', 'observed_on']):
            # Use errors='coerce' instead of 'ignore' for Pandas compatibility
            df[col] = pd.to_datetime(df[col], dayfirst=True, format='mixed', errors='coerce')
            # Only apply strftime to actual datetime objects (leaves NaT as is)
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')

    # Replace Pandas NaN/NaT with Python None so MySQL connector inserts NULL
    df = df.where(pd.notnull(df), None)
    
    # Build the dynamic SQL query based on dataframe columns
    cols = ", ".join([f"`{col}`" for col in df.columns])
    placeholders = ", ".join(["%s"] * len(df.columns))
    sql = f"INSERT INTO `{table_name}` ({cols}) VALUES ({placeholders})"
    
    # Convert dataframe to a list of tuples
    data = [tuple(row) for row in df.to_numpy()]
    
    cur.executemany(sql, data)
    return len(data)


def main():
    conn = get_connection()
    print("Connected to TiDB.")
    cur = conn.cursor()
    
    try:
        reset_seed_data(cur)
        
        # Order matters here due to foreign key constraints. Users must be inserted first, then accounts, budgets, transactions, receipt_items, alerts, predictions, and finally reference_prices.
        tables_to_load = {
            "users": "database/users.csv",
            "accounts": "database/accounts.csv",
            "budgets": "database/budgets.csv",
            "transactions": "database/transactions.csv",
            "receipt_items": "database/receipt_items.csv",
            "alerts": "database/alerts.csv",
            "predictions": "database/predictions.csv",
            "reference_prices": "database/reference_prices.csv"
        }
        
        for table, csv_file in tables_to_load.items():
            if not os.path.exists(csv_file):
                print(f"Skipping {table} - {csv_file} not found.")
                continue
                
            print(f"Loading {csv_file} into {table}...")
            df = pd.read_csv(csv_file)
            
            inserted_count = insert_dataframe(cur, df, table)
            print(f" -> Inserted {inserted_count} rows into `{table}`.")

        # Commit all the transactions at once
        conn.commit()
        print("\nSuccess! All CSV data has been seeded to the database.")
        
    except Exception as e:
        conn.rollback()
        print(f"\nError encountered, rolling back changes: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()