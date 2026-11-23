from sqlalchemy.orm import Session
from typing import List, Optional

from sqlalchemy import or_

from app.models.user import User
from app.models.rbac import UserRole, Role
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


# ---------- 账号管理（admin）CRUD ----------

def get_users_page(db: Session, pageNo: int = 1, pageSize: int = 20,
                   keyword: Optional[str] = None) -> dict:
    """
    分页查询账号列表（仅安全字段，不含 password_hash）：
    - keyword: 按姓名/邮箱关键字过滤（自动转义通配符）
    - 返回 {list, total, adminCount, memberCount, pageNo, pageSize}
    - 统计（total/adminCount/memberCount）跟随 keyword 过滤口径，与前端原行为一致
    - 角色按页聚合（IN 查询），避免 N+1
    """
    query = db.query(User)
    if keyword:
        query = query.filter(
            or_(
                User.name.contains(keyword, autoescape=True),
                User.email.contains(keyword, autoescape=True),
            )
        )

    total = query.count()

    # 管理员数：过滤集中挂 admin 角色的去重用户数（join 统计，不额外拉全量）
    admin_count = (
        query.with_entities(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.code == "admin")
        .distinct()
        .count()
    )
    member_count = total - admin_count

    # 当前页数据
    users = (
        query.order_by(User.id)
        .offset((pageNo - 1) * pageSize)
        .limit(pageSize)
        .all()
    )

    # 仅对当前页用户聚合角色（IN 一次查全）
    page_ids = [u.id for u in users]
    roles_map: dict = {}
    if page_ids:
        role_rows = (
            db.query(UserRole.user_id, Role.code)
            .join(Role, Role.id == UserRole.role_id)
            .filter(UserRole.user_id.in_(page_ids))
            .all()
        )
        for uid, code in role_rows:
            roles_map.setdefault(uid, []).append(code)

    return {
        "list": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "roles": roles_map.get(u.id, []),
                "has_password": bool(u.password_hash),
            }
            for u in users
        ],
        "total": total,
        "adminCount": admin_count,
        "memberCount": member_count,
        "pageNo": pageNo,
        "pageSize": pageSize,
    }


def delete_user(db: Session, user_id: int) -> bool:
    """删除账号：先清理 user_roles 关联，再删除用户本身。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return True


def reset_password(db: Session, user_id: int, new_password: str) -> User:
    """管理员重置指定账号密码（无需旧密码）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"用户 ID {user_id} 不存在")
    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user
