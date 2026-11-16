"""
RBAC 路由：角色管理 / 权限管理 / 用户角色分配 / 当前用户权限
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.core.security import get_current_user, require_role
from app.models.user import User
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


@router.get("/roles", summary="角色列表（含权限）")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取所有角色及其权限"""
    roles = crud_rbac.get_roles(db)
    result = []
    for r in roles:
        result.append({
            "id": r.id,
            "name": r.name,
            "code": r.code,
            "description": r.description,
            "permissions": [
                {"id": p.id, "name": p.name, "code": p.code, "type": p.type}
                for p in r.permissions
            ],
        })
    return result


@router.delete("/roles/{role_id}", summary="删除角色")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """删除角色（仅 admin）"""
    if not crud_rbac.delete_role(db, role_id):
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"message": "删除成功"}


@router.put("/roles/permissions", summary="给角色分配权限")
def assign_permissions(
    data: AssignPermissionsToRole,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """给角色重新分配权限（覆盖式，仅 admin）"""
    try:
        role = crud_rbac.assign_permissions_to_role(db, data.role_code, data.permission_codes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "role_code": role.code,
        "permissions": [p.code for p in role.permissions],
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
