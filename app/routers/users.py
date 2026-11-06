from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.crud import user as crud_user

router = APIRouter(prefix="/users", tags=["用户管理"])

@router.post("/", summary="创建用户")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    return crud_user.create_user(db=db, user=user)

@router.get("/", summary="获取用户列表")
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_user.get_users(db, skip=skip, limit=limit)

@router.get("/{user_id}", summary="获取单个用户")
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud_user.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user
