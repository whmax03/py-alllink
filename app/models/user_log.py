"""
姓名修改日志模型

记录账号姓名被谁在什么时间从 A 改成 B，供账号管理页「修改日志」查看。
"""
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

from app.database import Base


class UserNameChangeLog(Base):
    """姓名修改日志表"""
    __tablename__ = "user_name_change_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="被修改姓名的账号 ID")
    old_name = Column(String(100), nullable=True, comment="修改前姓名")
    new_name = Column(String(100), nullable=True, comment="修改后姓名")
    operator_id = Column(Integer, nullable=True, comment="操作人账号 ID")
    operator_name = Column(String(100), nullable=True, comment="操作人姓名")
    operator_email = Column(String(200), nullable=True, comment="操作人邮箱")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="操作时间")
