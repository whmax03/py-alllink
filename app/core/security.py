"""
安全工具模块：密码哈希 + JWT 令牌管理 + 权限依赖

认证错误码：
  10001 — 未提供 token（未登录）
  10002 — token 已过期或无效
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import bcrypt
from jose import JWTError, ExpiredSignatureError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv

from app.database import get_db
from app.models.user import User

load_dotenv()

# ---------- 配置 ----------
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 默认 24 小时

# ---------- OAuth2 ----------
# auto_error=False：不自动抛 401，让我们自己区分"没传 token"和"token 过期"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希（UTF-8 字节超 72 自动截断）"""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配"""
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT access_token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """解码 JWT token，区分过期和其他无效情况"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 10002, "message": "登录已过期，请重新登录"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 10002, "message": "Token 无效，请重新登录"},
        )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI 依赖：从 JWT token 解析并返回完整的 User 对象。
    - 没传 token → 10001（未登录）
    - token 过期/无效 → 10002（登录已过期）
    """
    # 没传 token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 10001, "message": "未登录，请先登录"},
        )

    payload = decode_access_token(token)
    email: Optional[str] = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 10002, "message": "Token 信息不完整，请重新登录"},
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 10002, "message": "用户不存在，请重新登录"},
        )
    return user


def require_role(role_code: str):
    """
    生成一个依赖，要求当前用户拥有指定角色。
    用法: @router.get("/...", dependencies=[Depends(require_role("admin"))])
    """
    def _check(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        from app.crud import rbac as crud_rbac
        role_codes, _ = crud_rbac.get_user_permissions(db, current_user.id)
        if role_code not in role_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 '{role_code}' 角色权限",
            )
        return current_user

    return _check


def require_permission(perm_code: str):
    """
    生成一个依赖，要求当前用户拥有指定权限编码。
    admin 角色自动拥有所有权限。
    """
    def _check(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        from app.crud import rbac as crud_rbac
        role_codes, perm_codes = crud_rbac.get_user_permissions(db, current_user.id)
        # admin 自动放行
        if "admin" in role_codes:
            return current_user
        if perm_code not in perm_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {perm_code}",
            )
        return current_user

    return _check
