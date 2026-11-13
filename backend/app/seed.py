"""Creates demo accounts for local testing. Run from backend/: python -m app.seed"""

from sqlalchemy import select

from app.controllers.auth_controller import hash_password
from app.database import Base, SessionLocal, engine
from app.models.user import User

# Local development only; never run this against a shared or production database.
DEMO_USERS = [
    {"first_name": "Demo", "last_name": "Student", "email": "demo@example.com", "password": "DemoPass123"},
    {"first_name": "Test", "last_name": "User", "email": "test@example.com", "password": "TestPass123"},
]


def seed():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for demo in DEMO_USERS:
            if db.scalar(select(User).where(User.email == demo["email"])):
                print(f"exists   {demo['email']}")
                continue

            db.add(
                User(
                    first_name=demo["first_name"],
                    last_name=demo["last_name"],
                    email=demo["email"],
                    password_hash=hash_password(demo["password"]),
                )
            )
            print(f"created  {demo['email']}")
        db.commit()


if __name__ == "__main__":
    seed()
