"""
用户管理路由（账号管理页后端接口）：
- 所有接口要求 admin 角色（require_role 守卫）
- 新增账号（姓名 + 邮箱 + 密码）/ 查询账号 / 删除账号 / 重置账号密码
- 所有返回只包含安全字段（不含 password_hash）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.schemas.user import UserRegister, PasswordReset
from app.crud import user as crud_user
from app.crud import rbac as crud_rbac
from app.core.security import require_role
from app.models.user import User

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.post("/", summary="新增账号（admin）")
def create_user(
    user: UserRegister,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """新增账号：姓名 + 邮箱 + 密码。邮箱不能重复；新账号默认无角色，需在 RBAC 中分配。"""
    try:
        db_user = crud_user.register_user(db=db, user_data=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": db_user.id,
        "name": db_user.name,
        "email": db_user.email,
    }


@router.get("/", summary="查询账号列表（admin）")
def read_users(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=200, description="每页条数，1-200"),
    keyword: Optional[str] = Query(None, description="按姓名/邮箱关键字过滤"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """
    分页查询账号列表（仅安全字段，不含 password_hash）：
    - pageNo/pageSize 分页；keyword 按姓名/邮箱模糊过滤
    - 返回 list + total + adminCount + memberCount + pageNo + pageSize
    """
    return crud_user.get_users_page(
        db, pageNo=pageNo, pageSize=pageSize, keyword=keyword,
    )


@router.get("/{user_id}", summary="获取单个账号（admin）")
def read_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """获取单个账号信息（安全字段）。"""
    db_user = crud_user.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return {
        "id": db_user.id,
        "name": db_user.name,
        "email": db_user.email,
    }


@router.delete("/{user_id}", summary="删除账号（admin）")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role("admin")),
):
    """删除账号：同时清理其角色关联；不允许删除当前登录账号；admin 角色账号禁止删除。"""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    target_roles = crud_rbac.get_user_roles(db, user_id)
    if any(r.code == "admin" for r in target_roles):
        raise HTTPException(status_code=400, detail="admin 角色账号禁止删除")
    if not crud_user.delete_user(db, user_id):
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"message": "删除成功"}


@router.put("/{user_id}/password", summary="重置账号密码（admin）")
def reset_password(
    user_id: int,
    data: PasswordReset,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """管理员重置指定账号密码（无需旧密码）。"""
    try:
        crud_user.reset_password(db, user_id, data.new_password)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "密码重置成功"}
