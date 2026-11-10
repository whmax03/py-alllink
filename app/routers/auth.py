"""
认证路由：注册 / 登录 / 修改密码
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import UserRegister, UserLogin, ChangePassword, TokenResponse, UserResponse
from app.crud import user as crud_user
from app.core.security import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["认证管理"])


@router.post("/register", summary="用户注册")
def register(user: UserRegister, db: Session = Depends(get_db)):
    """
    用户注册接口。
    - 必须提供 name、email、password
    - 邮箱不能重复
    """
    try:
        db_user = crud_user.register_user(db=db, user_data=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": db_user.id,
        "name": db_user.name,
        "email": db_user.email,
    }


@router.post("/login", summary="用户登录")
def login(user: UserLogin, db: Session = Depends(get_db)):
    """
    用户登录接口。
    - 验证邮箱和密码
    - 成功返回 access_token（JWT）
    """
    db_user = crud_user.authenticate_user(db, email=user.email, password=user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    # 生成 JWT token
    access_token = create_access_token(
        data={"sub": db_user.email, "name": db_user.name}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "name": db_user.name,
            "email": db_user.email,
        },
    }


@router.post("/change-password", summary="修改密码")
def change_password(data: ChangePassword, db: Session = Depends(get_db)):
    """
    修改密码接口。
    - 需要提供 email、old_password、new_password
    - 验证旧密码后更新为新密码
    """
    try:
        db_user = crud_user.update_password(
            db,
            email=data.email,
            old_password=data.old_password,
            new_password=data.new_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "密码修改成功"}
