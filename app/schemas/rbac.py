"""
RBAC Schema：角色/权限的请求和响应模型
"""
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


# ---------- 权限 ----------

class PermissionBase(BaseModel):
    name: str
    code: str
    type: str  # page / tab / data
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionResponse(PermissionBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- 角色 ----------

class RoleBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    permission_codes: List[str] = []  # 创建角色时同时分配权限


class RoleResponse(RoleBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleResponse):
    """角色 + 权限列表"""
    permissions: List[PermissionResponse] = []


# ---------- 用户角色分配 ----------

class AssignRole(BaseModel):
    """给用户分配角色"""
    user_id: int
    role_codes: List[str]  # 角色编码列表


class AssignPermissionsToRole(BaseModel):
    """给角色分配权限"""
    role_code: str
    permission_codes: List[str]


# ---------- 用户权限返回 ----------

class UserPermissionsResponse(BaseModel):
    """当前登录用户的权限信息"""
    user_id: int
    name: str
    email: str
    roles: List[str] = []  # 角色编码列表
    permissions: List[str] = []  # 权限编码列表（去重）
