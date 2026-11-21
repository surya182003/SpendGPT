
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.controllers.ai_controller import router as ai_router
from app.controllers.auth_controller import router as auth_router
from app.controllers.category_controller import router as category_router
from app.controllers.receipt_controller import router as receipt_router
from app.controllers.transaction_controller import router as transaction_router
from app.controllers.budget_controller import router as budget_router
from app.database import Base, engine

from app.models.user import User
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.receipt_item import ReceiptItem
from app.models.budget import Budget


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SpendGPT API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(category_router)
app.include_router(transaction_router)
app.include_router(receipt_router)
app.include_router(ai_router)
app.include_router(budget_router)


@app.get("/health")
def health():
    return {"status": "ok"}
