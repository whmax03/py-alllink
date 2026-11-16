"""
RBAC CRUD：角色/权限/用户角色分配的数据库操作
"""
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from app.models.rbac import Role, Permission, UserRole, role_permissions
from app.models.user import User
from app.schemas.rbac import RoleCreate, PermissionCreate


# ========== 权限 CRUD ==========

def create_permission(db: Session, perm: PermissionCreate) -> Permission:
    """创建权限"""
    existing = db.query(Permission).filter(Permission.code == perm.code).first()
    if existing:
        raise ValueError(f"权限编码 '{perm.code}' 已存在")
    db_perm = Permission(
        name=perm.name,
        code=perm.code,
        type=perm.type,
        description=perm.description,
    )
    db.add(db_perm)
    db.commit()
    db.refresh(db_perm)
    return db_perm


def get_permissions(db: Session, perm_type: Optional[str] = None) -> List[Permission]:
    """获取权限列表，可按类型过滤"""
    query = db.query(Permission)
    if perm_type:
        query = query.filter(Permission.type == perm_type)
    return query.all()


def get_permission_by_code(db: Session, code: str) -> Optional[Permission]:
    return db.query(Permission).filter(Permission.code == code).first()


def delete_permission(db: Session, perm_id: int) -> bool:
    perm = db.query(Permission).filter(Permission.id == perm_id).first()
    if not perm:
        return False
    db.delete(perm)
    db.commit()
    return True


# ========== 角色 CRUD ==========

def create_role(db: Session, role: RoleCreate) -> Role:
    """创建角色，并同时分配权限"""
    existing = db.query(Role).filter(Role.code == role.code).first()
    if existing:
        raise ValueError(f"角色编码 '{role.code}' 已存在")

    db_role = Role(
        name=role.name,
        code=role.code,
        description=role.description,
    )
    db.add(db_role)
    db.flush()  # 拿到 id

    # 分配权限
    if role.permission_codes:
        perms = db.query(Permission).filter(
            Permission.code.in_(role.permission_codes)
        ).all()
        for perm in perms:
            db_role.permissions.append(perm)

    db.commit()
    db.refresh(db_role)
    return db_role


def get_roles(db: Session) -> List[Role]:
    """获取所有角色（含权限）"""
    return db.query(Role).options(joinedload(Role.permissions)).all()


def get_role_by_code(db: Session, code: str) -> Optional[Role]:
    return db.query(Role).filter(Role.code == code).first()


def delete_role(db: Session, role_id: int) -> bool:
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        return False
    db.delete(role)
    db.commit()
    return True


def assign_permissions_to_role(db: Session, role_code: str, permission_codes: List[str]) -> Role:
    """给角色分配权限（覆盖式：先清除再重新分配）"""
    role = db.query(Role).filter(Role.code == role_code).first()
    if not role:
        raise ValueError(f"角色 '{role_code}' 不存在")

    # 清除旧权限
    role.permissions.clear()

    # 分配新权限
    if permission_codes:
        perms = db.query(Permission).filter(
            Permission.code.in_(permission_codes)
        ).all()
        for perm in perms:
            role.permissions.append(perm)

    db.commit()
    db.refresh(role)
    return role


# ========== 用户角色 ==========

def assign_roles_to_user(db: Session, user_id: int, role_codes: List[str]) -> User:
    """给用户分配角色（覆盖式）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"用户 ID {user_id} 不存在")

    # 清除旧角色
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()

    # 分配新角色
    for code in role_codes:
        role = db.query(Role).filter(Role.code == code).first()
        if not role:
            raise ValueError(f"角色 '{code}' 不存在")
        db.add(UserRole(user_id=user_id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return user


def get_user_roles(db: Session, user_id: int) -> List[Role]:
    """获取用户的角色列表"""
    return (
        db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .all()
    )


def get_user_permissions(db: Session, user_id: int):
    """
    获取用户的所有权限编码（去重）。
    返回 (roles, permissions) 二元组。
    """
    roles = get_user_roles(db, user_id)
    role_codes = [r.code for r in roles]

    perm_codes = set()
    for role in roles:
        for perm in role.permissions:
            perm_codes.add(perm.code)

    return role_codes, list(perm_codes)


def is_admin(db: Session, user_id: int) -> bool:
    """检查用户是否有 admin 角色"""
    roles = get_user_roles(db, user_id)
    return any(r.code == "admin" for r in roles)
