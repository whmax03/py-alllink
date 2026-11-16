"""
认证路由：注册 / 登录 / 修改密码
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import UserRegister, UserLogin, ChangePassword
from app.crud import user as crud_user
from app.crud import rbac as crud_rbac
from app.core.security import create_access_token, get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["认证管理"])


@router.post("/register", summary="用户注册")
def register(user: UserRegister, db: Session = Depends(get_db)):
    """
    用户注册接口。
    - 必须提供 name、email、password
    - 邮箱不能重复
    - 默认注册的用户没有角色，需要 admin 分配
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
    - 成功返回 access_token（JWT）+ 用户信息 + 角色
    """
    db_user = crud_user.authenticate_user(db, email=user.email, password=user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    # 获取用户角色
    roles = crud_rbac.get_user_roles(db, db_user.id)
    role_codes = [r.code for r in roles]

    # 生成 JWT token（角色信息写入 token）
    access_token = create_access_token(
        data={"sub": db_user.email, "name": db_user.name, "roles": role_codes}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "name": db_user.name,
            "email": db_user.email,
            "roles": role_codes,
        },
    }


@router.post("/change-password", summary="修改密码")
def change_password(data: ChangePassword, db: Session = Depends(get_db)):
    """修改密码接口"""
    try:
        crud_user.update_password(
            db,
            email=data.email,
            old_password=data.old_password,
            new_password=data.new_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "密码修改成功"}


@router.get("/me", summary="获取当前登录用户信息")
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息（需要 token）"""
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
    }
