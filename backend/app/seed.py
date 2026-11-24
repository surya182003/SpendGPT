
"""Creates demo accounts and default categories for local testing.
Run from backend/: python -m app.seed
"""

import csv
from pathlib import Path

from sqlalchemy import select

from app.controllers.auth_controller import hash_password
from app.database import Base, SessionLocal, engine
from app.models.user import User
from app.models.category import Category


# Local development only; never run this against a shared or production database.

DEMO_USERS = [
    {
        "first_name": "Demo",
        "last_name": "Student",
        "email": "demo@example.com",
        "password": "DemoPass123",
    },
    {
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "password": "TestPass123",
    },
]

CATEGORY_TYPES = {
    "Groceries": "Essential",
    "Rent": "Essential",
    "Utilities": "Essential",
    "Transport": "Essential",
    "Health": "Essential",
    "Eating Out": "Discretionary",
    "Shopping": "Discretionary",
    "Entertainment": "Discretionary",
    "Subscriptions": "Discretionary",
}

CATEGORIES_FILE = (
    Path(__file__).resolve().parents[2] / "database" / "categories.csv"
)


def seed():
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:

        # Seed default categories from the CSV file.
        with open(CATEGORIES_FILE, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                category_id = int(row["category_id"])
                category_name = row["category_name"]
                spend_type = CATEGORY_TYPES.get(category_name)

                if spend_type is None:
                    print(f"skipped   {category_name}: no spend type defined")
                    continue

                existing_id = db.get(Category, category_id)
                existing_name = db.scalar(
                    select(Category).where(
                        Category.category_name == category_name
                    )
                )

                if existing_id or existing_name:
                    print(f"exists    {category_name}")
                    continue

                db.add(
                    Category(
                        category_id=category_id,
                        category_name=category_name,
                        spend_type=spend_type,
                    )
                )
                print(f"created   category: {category_name}")

        # Seed demo users.
        for demo in DEMO_USERS:
            if db.scalar(select(User).where(User.email == demo["email"])):
                print(f"exists    {demo['email']}")
                continue

            db.add(
                User(
                    first_name=demo["first_name"],
                    last_name=demo["last_name"],
                    email=demo["email"],
                    password_hash=hash_password(demo["password"]),
                )
            )
            print(f"created   user: {demo['email']}")

        db.commit()


if __name__ == "__main__":
    seed()
