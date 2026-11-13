import os
from pathlib import Path

import certifi
import mysql.connector
from dotenv import load_dotenv

env_path = Path(__file__).parent /  ".env"
print("Looking for .env at:", env_path, "- exists:", env_path.exists()) # make sure the .env file is in the same directory as this script
# i had trouble with the .env file not being found, so i added this print statement to help debug
# backend dev please look at this and make sure the .env file is in the same directory as this script, and that it contains the correct credentials for your TiDB database
load_dotenv(env_path)

conn = mysql.connector.connect(
    host=os.getenv("TIDB_HOST"),
    port=int(os.getenv("TIDB_PORT", 4000)),
    user=os.getenv("TIDB_USER"),
    password=os.getenv("TIDB_PASSWORD"),
    database=os.getenv("TIDB_DATABASE", "student_spend_db"),
    ssl_ca=certifi.where(),
    ssl_verify_cert=True,
    ssl_verify_identity=True,
)

cur = conn.cursor()
cur.execute("SELECT category_id, category_name, spend_type FROM categories")
categories = cur.fetchall()

print("Connected! Categories in the database:")
for category_id, name, spend_type in categories:
    print(f"{category_id}: {name} ({spend_type})")

cur.execute("SELECT * FROM users")
users = cur.fetchall()

print("first 5 users in the database:")
for user in users[:5]:
    print(user)

cur.close()
conn.close()