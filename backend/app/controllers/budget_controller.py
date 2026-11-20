
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.budget import Budget
from app.models.category import Category
from app.models.user import User
from app.schemas.budget_schema import BudgetCreate, BudgetResponse


router = APIRouter(prefix="/api/budgets", tags=["budgets"])


# Check whether the user exists
def validate_user(db: Session, user_id: int):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )


# Check whether the category exists
def validate_category(db: Session, category_id: int | None):
    if category_id is not None:
        category = db.get(Category, category_id)

        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )


# Get a budget belonging to a specific user
def get_user_budget(db: Session, budget_id: int, user_id: int):
    statement = select(Budget).where(
        Budget.budget_id == budget_id,
        Budget.user_id == user_id
    )

    budget = db.scalar(statement)

    if budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found"
        )

    return budget


# Check whether the requested budget period overlaps an existing one
def check_budget_period(
    db: Session,
    user_id: int,
    category_id: int | None,
    start_date,
    end_date,
    exclude_budget_id: int | None = None
):
    statement = select(Budget).where(
        Budget.user_id == user_id,
        Budget.category_id == category_id,
        Budget.start_date <= end_date,
        Budget.end_date >= start_date
    )

    if exclude_budget_id is not None:
        statement = statement.where(
            Budget.budget_id != exclude_budget_id
        )

    existing_budget = db.scalar(statement)

    if existing_budget is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A budget already exists for an overlapping period"
        )


@router.post(
    "/",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED
)
def create_budget(
    user_id: int,
    payload: BudgetCreate,
    db: Session = Depends(get_db)
):
    validate_user(db, user_id)
    validate_category(db, payload.category_id)

    check_budget_period(
        db,
        user_id,
        payload.category_id,
        payload.start_date,
        payload.end_date
    )

    budget = Budget(
        user_id=user_id,
        category_id=payload.category_id,
        amount_limit=payload.amount_limit,
        start_date=payload.start_date,
        end_date=payload.end_date
    )

    db.add(budget)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Budget could not be created due to a database constraint"
        ) from None

    db.refresh(budget)

    return budget


@router.get(
    "/user/{user_id}",
    response_model=list[BudgetResponse]
)
def get_user_budgets(
    user_id: int,
    db: Session = Depends(get_db)
):
    validate_user(db, user_id)

    statement = (
        select(Budget)
        .where(Budget.user_id == user_id)
        .order_by(Budget.start_date.desc())
    )

    budgets = db.scalars(statement).all()

    return budgets


# Get a specific budget
@router.get(
    "/{budget_id}",
    response_model=BudgetResponse
)
def get_budget(
    budget_id: int,
    user_id: int,
    db: Session = Depends(get_db)
):
    return get_user_budget(db, budget_id, user_id)


# Update an existing budget
@router.put(
    "/{budget_id}",
    response_model=BudgetResponse
)
def update_budget(
    budget_id: int,
    user_id: int,
    payload: BudgetCreate,
    db: Session = Depends(get_db)
):
    validate_user(db, user_id)

    budget = get_user_budget(db, budget_id, user_id)

    validate_category(db, payload.category_id)

    check_budget_period(
        db,
        user_id,
        payload.category_id,
        payload.start_date,
        payload.end_date,
        exclude_budget_id=budget_id
    )

    budget.category_id = payload.category_id
    budget.amount_limit = payload.amount_limit
    budget.start_date = payload.start_date
    budget.end_date = payload.end_date

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Budget could not be updated due to a database constraint"
        ) from None

    db.refresh(budget)

    return budget


# Delete an existing budget
@router.delete("/{budget_id}")
def delete_budget(
    budget_id: int,
    user_id: int,
    db: Session = Depends(get_db)
):
    budget = get_user_budget(db, budget_id, user_id)

    db.delete(budget)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Budget could not be deleted due to a database constraint"
        ) from None

    return {"message": "Budget deleted successfully"}