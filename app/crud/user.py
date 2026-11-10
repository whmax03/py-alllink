from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserCreate, UserRegister
from app.core.security import hash_password, verify_password


def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(User).offset(skip).limit(limit).all()


def create_user(db: Session, user: UserCreate):
    db_user = User(name=user.name, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# ---------- 认证相关 CRUD ----------

def register_user(db: Session, user_data: UserRegister) -> User:
    """注册新用户：检查邮箱是否已存在，创建用户并存储密码哈希"""
    existing = get_user_by_email(db, email=user_data.email)
    if existing:
        raise ValueError("该邮箱已被注册")

    db_user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """
    验证用户登录：根据邮箱查找用户并校验密码。
    成功返回 User 对象，失败返回 None。
    """
    user = get_user_by_email(db, email=email)
    if not user:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def update_password(db: Session, email: str, old_password: str, new_password: str) -> User:
    """
    修改密码：验证旧密码后更新为新密码哈希。
    """
    user = authenticate_user(db, email=email, password=old_password)
    if not user:
        raise ValueError("邮箱或旧密码不正确")

    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user
