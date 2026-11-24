"""
RBAC CRUD：角色/权限/用户角色分配的数据库操作
"""
from sqlalchemy import func, or_
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


def get_roles_page(db: Session, pageNo: int = 1, pageSize: int = 20,
                   keyword: Optional[str] = None) -> dict:
    """
    分页查询角色列表（含权限与绑定账号数）。
    - keyword: 按名称/编码模糊过滤（自动转义通配符）
    - 返回 {list, total, pageNo, pageSize}；list 元素含 user_count、permissions
    """
    query = db.query(Role)
    if keyword:
        query = query.filter(
            or_(
                Role.name.contains(keyword, autoescape=True),
                Role.code.contains(keyword, autoescape=True),
            )
        )

    total = query.count()
    roles = (
        query.options(joinedload(Role.permissions))
        .order_by(Role.id)
        .offset((pageNo - 1) * pageSize)
        .limit(pageSize)
        .all()
    )

    # 绑定账号数：一次 group by 拉全部，避免逐角色查询
    user_counts = get_role_user_counts(db)

    return {
        "list": [
            {
                "id": r.id,
                "name": r.name,
                "code": r.code,
                "description": r.description,
                "user_count": user_counts.get(r.id, 0),
                "permissions": [
                    {"id": p.id, "name": p.name, "code": p.code, "type": p.type}
                    for p in r.permissions
                ],
            }
            for r in roles
        ],
        "total": total,
        "pageNo": pageNo,
        "pageSize": pageSize,
    }


def get_role_by_code(db: Session, code: str) -> Optional[Role]:
    return db.query(Role).filter(Role.code == code).first()


def delete_role(db: Session, role_id: int) -> bool:
    """删除角色：先清理用户角色关联（user_roles 无级联），再删除角色本身。"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        return False
    db.query(UserRole).filter(UserRole.role_id == role_id).delete()
    db.delete(role)
    db.commit()
    return True


def update_role(db: Session, role_id: int, name: str, code: str, description: Optional[str]) -> Role:
    """更新角色（名称/简称/描述）；admin 角色由路由层拦截禁止更新。"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise ValueError(f"角色 ID {role_id} 不存在")
    if code != role.code:
        dup = db.query(Role).filter(Role.code == code).first()
        if dup:
            raise ValueError(f"角色简称 '{code}' 已存在")
    role.name = name
    role.code = code
    role.description = description
    db.commit()
    db.refresh(role)
    return role


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

def get_role_user_counts(db: Session) -> dict:
    """按角色统计绑定账号数：{role_id: count}（一条 group by 查询，避免 N+1）"""
    rows = (
        db.query(UserRole.role_id, func.count(UserRole.user_id))
        .group_by(UserRole.role_id)
        .all()
    )
    return {role_id: count for role_id, count in rows}


def get_role_users(db: Session, role_id: int) -> List[User]:
    """获取绑定某角色的账号列表（按 id 排序，输出字段由路由层白名单控制）"""
    return (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .filter(UserRole.role_id == role_id)
        .order_by(User.id)
        .all()
    )


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
    admin 角色直接拥有全部权限（免配置，权限页禁止修改 admin）。
    """
    roles = get_user_roles(db, user_id)
    role_codes = [r.code for r in roles]

    if "admin" in role_codes:
        all_codes = [p.code for p in db.query(Permission).all()]
        return role_codes, all_codes

    perm_codes = set()
    for role in roles:
        for perm in role.permissions:
            perm_codes.add(perm.code)

    return role_codes, list(perm_codes)


def is_admin(db: Session, user_id: int) -> bool:
    """检查用户是否有 admin 角色"""
    roles = get_user_roles(db, user_id)
    return any(r.code == "admin" for r in roles)


# ========== 数据范围（平台权限） ==========

def get_visible_platforms(db: Session, user_id: int) -> Optional[List[str]]:
    """
    解析用户可见的数据平台白名单（库存数据隔离的依据）。
    - admin 角色 → None（不过滤，看全部）
    - 非 admin → 从其权限码提取 platform:xxx → [xxx, ...]
      - 无任何 platform 权限 → 空列表 []（看不到任何库存数据）
    - 过滤在库存查询层强制生效，前端传参只能缩小、不能扩大范围
    """
    role_codes, perm_codes = get_user_permissions(db, user_id)
    if "admin" in role_codes:
        return None
    platforms = [
        code.split(":", 1)[1]
        for code in perm_codes
        if code.startswith("platform:") and len(code.split(":", 1)) == 2
    ]
    return platforms
