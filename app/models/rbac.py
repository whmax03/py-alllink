"""
RBAC 权限模型：角色 + 权限 + 关联表

权限类型:
  - page: 页面权限（控制能否访问某个页面路由）
  - tab:  Tab显示权限（控制页面内某个标签页是否显示）
  - data: 数据权限（控制能看到哪些数据范围）
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Table
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


# ---------- 角色-权限 多对多关联 ----------
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, comment="角色名称")
    code = Column(String(50), unique=True, index=True, nullable=False, comment="角色编码")
    description = Column(String(200), nullable=True, comment="角色描述")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    permissions = relationship("Permission", secondary=role_permissions, lazy="selectin")


class Permission(Base):
    """
    权限表
    type: page / tab / data
    code: 权限编码，如 page:inventory:domestic、tab:transit 等
    """
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="权限名称")
    code = Column(String(100), unique=True, index=True, nullable=False, comment="权限编码")
    type = Column(String(20), nullable=False, comment="权限类型: page/tab/data")
    description = Column(String(200), nullable=True, comment="权限描述")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")


class UserRole(Base):
    """用户-角色 关联表"""
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, comment="分配时间")
