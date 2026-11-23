"""
Database Transaction & Health Smoke Test (Corrected)
Tests:
1. Basic connection and read access.
2. Transaction ROLLBACK (ensures aborted changes don't persist).
3. Transaction COMMIT (ensures successful changes save properly). # i think mysql.connector automatically manages transactions when autocommit is off, meaning a transaction is already considered "in progress" by default.
"""

import os
import certifi
import mysql.connector
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

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

def run_tests():
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Test 1: Read check
        print("\n[Test 1/3] Running basic read check...")
        cur.execute("SELECT COUNT(*) FROM users;")
        user_count = cur.fetchone()[0]
        print(f"Read successful! found {user_count} users in the database.")

        # Test 2: Transaction Rollback Test
        print("\n[Test 2/3] Testing transaction ROLLBACK behavior...")
        
        # Insert a fake test user (transaction starts automatically)
        cur.execute(
            """INSERT INTO users (first_name, last_name, email, password_hash, base_currency, monthly_income, savings_goal)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            ("Rollback", "Test", "rollback.test@spendgpt.dev", "fakehash", "EUR", 1000, 100)
        )
        
        # Intentionally rolling back to discard the insert
        conn.rollback()
        
        cur.execute("SELECT COUNT(*) FROM users WHERE email = 'rollback.test@spendgpt.dev';")
        exists = cur.fetchone()[0]
        if exists == 0:
            print(" Rollback test passed! Uncommitted changes were successfully discarded.")
        else:
            print(" Rollback test failed! Data persisted despite rollback.")

        # Test 3: Transaction Commit Test
        print("\n[Test 3/3] Testing transaction COMMIT behavior...")
        
        cur.execute(
            """INSERT INTO users (first_name, last_name, email, password_hash, base_currency, monthly_income, savings_goal)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            ("Commit", "Test", "commit.test@spendgpt.dev", "fakehash", "EUR", 1000, 100)
        )
        
        # Committing the transaction to save it
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM users WHERE email = 'commit.test@spendgpt.dev';")
        exists = cur.fetchone()[0]
        if exists == 1:
            print(" Commit test passed! Changes were successfully saved.")
            
            # Cleaning up our test user
            cur.execute("DELETE FROM users WHERE email = 'commit.test@spendgpt.dev';")
            conn.commit()
            print(" cleaned up test user.")
        else:
            print(" commit test failed! Data was not saved.")

        print("\nall database transaction tests completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n Test failed with error: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_tests()


# ---------------------------------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------------------------------

#                           TEST RESULTS 

#[Test 1/3] Running basic read check...
#Read successful! found 5 users in the database.

# [Test 2/3] Testing transaction ROLLBACK behavior...
# Rollback test passed! Uncommitted changes were successfully discarded.

# [Test 3/3] Testing transaction COMMIT behavior...
#Commit test passed! Changes were successfully saved.
# `Cleaned up test user.

# all database transaction tests completed successfully!

# ----------------------------------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------------------------------