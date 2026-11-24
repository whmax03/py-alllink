"""
RBAC 路由：角色管理 / 权限管理 / 用户角色分配 / 当前用户权限
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.core.security import get_current_user, require_role
from app.models.user import User
from app.models.rbac import Role, Permission
from app.schemas.rbac import (
    RoleCreate, RoleResponse, RoleWithPermissions,
    PermissionCreate, PermissionResponse,
    AssignRole, AssignPermissionsToRole,
    UserPermissionsResponse,
)
from app.crud import rbac as crud_rbac

router = APIRouter(prefix="/rbac", tags=["权限管理"])


# ========== 权限管理 ==========

@router.post("/permissions", summary="创建权限")
def create_permission(
    perm: PermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """创建权限（仅 admin）"""
    try:
        result = crud_rbac.create_permission(db, perm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": result.id,
        "name": result.name,
        "code": result.code,
        "type": result.type,
        "description": result.description,
    }


@router.get("/permissions", summary="权限列表")
def list_permissions(
    perm_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取权限列表，可按 type 过滤（page/tab/data）"""
    perms = crud_rbac.get_permissions(db, perm_type=perm_type)
    return [
        {
            "id": p.id,
            "name": p.name,
            "code": p.code,
            "type": p.type,
            "description": p.description,
        }
        for p in perms
    ]


@router.delete("/permissions/{perm_id}", summary="删除权限")
def delete_permission(
    perm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """删除权限（仅 admin）"""
    if not crud_rbac.delete_permission(db, perm_id):
        raise HTTPException(status_code=404, detail="权限不存在")
    return {"message": "删除成功"}


# ========== 角色管理 ==========

@router.post("/roles", summary="创建角色")
def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """创建角色并可选分配权限（仅 admin）"""
    try:
        result = crud_rbac.create_role(db, role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": result.id,
        "name": result.name,
        "code": result.code,
        "description": result.description,
        "permissions": [p.code for p in result.permissions],
    }


@router.get("/roles", summary="角色列表（含权限与绑定账号数，分页）")
def list_roles(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(100, ge=1, le=500, description="每页条数，默认100基本等同全量"),
    keyword: Optional[str] = Query(None, description="按名称/编码模糊过滤"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    分页查询角色及其权限，含每个角色绑定的账号数（角色管理页绑定账号列）。
    返回 list + total + pageNo + pageSize。
    """
    return crud_rbac.get_roles_page(db, pageNo=pageNo, pageSize=pageSize, keyword=keyword)


@router.delete("/roles/{role_id}", summary="删除角色")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """删除角色（仅 admin；admin 角色本身禁止删除，同时清理用户角色关联）"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.code == "admin":
        raise HTTPException(status_code=400, detail="admin 角色禁止删除")
    if not crud_rbac.delete_role(db, role_id):
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"message": "删除成功"}


@router.put("/roles/permissions", summary="给角色分配权限")
def assign_permissions(
    data: AssignPermissionsToRole,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """给角色重新分配权限（覆盖式，仅 admin）；admin 角色拥有全部权限，禁止修改"""
    if data.role_code == "admin":
        raise HTTPException(status_code=400, detail="admin 角色拥有全部权限，禁止修改")
    try:
        role = crud_rbac.assign_permissions_to_role(db, data.role_code, data.permission_codes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "role_code": role.code,
        "permissions": [p.code for p in role.permissions],
    }


@router.put("/roles/{role_id}", summary="更新角色（名称/简称/描述）")
def update_role(
    role_id: int,
    data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """更新角色名称/简称/描述（仅 admin；admin 角色本身禁止修改）"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.code == "admin":
        raise HTTPException(status_code=400, detail="admin 角色禁止修改")
    try:
        result = crud_rbac.update_role(db, role_id, data.name, data.code, data.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": result.id,
        "name": result.name,
        "code": result.code,
        "description": result.description,
        "permissions": [p.code for p in result.permissions],
    }


@router.get("/roles/{role_id}/users", summary="查询角色绑定的账号列表")
def get_role_users(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    查询绑定某角色的账号列表（仅 admin；角色管理页点击绑定账号数量弹窗）。
    输出白名单字段（不含密码哈希等敏感信息）。
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    users = crud_rbac.get_role_users(db, role_id)
    return {
        "role": {"id": role.id, "name": role.name, "code": role.code},
        "total": len(users),
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "roles": [r.code for r in crud_rbac.get_user_roles(db, u.id)],
            }
            for u in users
        ],
    }


@router.get("/roles/{role_id}/permissions", summary="查询角色权限详情")
def get_role_permissions_detail(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询某个角色的权限详情（权限管理页「权限详情」面板）：
    - 角色基本信息（id/name/code/description）
    - 权限明细列表（含 name/code/type）
    - admin 角色返回全库权限（与登录/me 口径一致）
    """
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role.code == "admin":
        # admin 拥有全部权限（免维护口径）
        perms = db.query(Permission).all()
    else:
        perms = role.permissions

    return {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "description": role.description,
        "is_admin": role.code == "admin",
        "permissions": [
            {"id": p.id, "name": p.name, "code": p.code, "type": p.type}
            for p in perms
        ],
    }

# ========== 用户角色分配 ==========

@router.put("/users/roles", summary="给用户分配角色")
def assign_user_roles(
    data: AssignRole,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """给用户分配角色（覆盖式，仅 admin）"""
    try:
        user = crud_rbac.assign_roles_to_user(db, data.user_id, data.role_codes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "user_id": user.id,
        "roles": data.role_codes,
    }


@router.get("/users/{user_id}/roles", summary="查询用户角色")
def get_user_roles(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某个用户的角色列表"""
    roles = crud_rbac.get_user_roles(db, user_id)
    return [
        {"id": r.id, "name": r.name, "code": r.code}
        for r in roles
    ]


# ========== 当前用户权限 ==========

@router.get("/me/permissions", summary="获取当前用户权限")
def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前登录用户的角色和权限编码列表。
    前端可用此接口控制页面/tab/数据的显示。
    """
    role_codes, perm_codes = crud_rbac.get_user_permissions(db, current_user.id)
    return {
        "user_id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "roles": role_codes,
        "permissions": perm_codes,
    }
