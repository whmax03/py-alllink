"""
用户管理路由（账号管理页后端接口）：
- 所有接口要求 admin 角色（require_role 守卫）
- 新增账号（姓名 + 邮箱 + 密码）/ 查询账号 / 删除账号 / 重置账号密码 / 修改姓名 + 姓名修改日志
- 所有返回只包含安全字段（不含 password_hash）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.schemas.user import UserRegister, PasswordReset, UserNameUpdate
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


@router.put("/{user_id}/name", summary="修改账号姓名（admin）")
def update_user_name(
    user_id: int,
    data: UserNameUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role("admin")),
):
    """
    修改账号姓名，并记录修改日志（修改前/修改后/操作人/操作时间）。

    - admin 角色账号不支持修改姓名
    - 姓名长度 2-20 个字符，且不能与当前姓名相同
    """
    target_roles = crud_rbac.get_user_roles(db, user_id)
    if any(r.code == "admin" for r in target_roles):
        raise HTTPException(status_code=400, detail="admin 账号不支持修改姓名")

    try:
        result = crud_user.update_name(
            db, user_id=user_id, new_name=data.name, operator=current_admin,
        )
    except ValueError as e:
        msg = str(e)
        status_code = 404 if "不存在" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg)

    return result


@router.get("/{user_id}/name-logs", summary="姓名修改日志（admin）")
def read_user_name_logs(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """查询指定账号的姓名修改日志（按操作时间倒序，最多 200 条）。"""
    if crud_user.get_user(db, user_id=user_id) is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"list": crud_user.get_name_logs(db, user_id=user_id)}
