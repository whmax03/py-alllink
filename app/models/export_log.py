"""
库存导出审计日志模型

导出会把数据带离系统，属于敏感操作。记录：谁、什么时候、导出了哪个仓（国内/海外）、
导出范围（全部/仅已筛选）、筛选条件原文、导出条数，便于事后审计追责。
"""
from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime

from app.database import Base


class InventoryExportLog(Base):
    """库存导出审计日志表"""
    __tablename__ = "inventory_export_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True, comment="导出人账号 ID")
    user_name = Column(String(100), nullable=True, comment="导出人姓名")
    user_email = Column(String(200), nullable=True, comment="导出人邮箱")
    scope = Column(String(20), nullable=False, comment="导出仓类型：domestic / overseas")
    mode = Column(String(20), nullable=False, comment="导出范围：all（全量）/ filtered（按筛选）")
    filters = Column(Text, nullable=True, comment="筛选条件 JSON 原文")
    row_count = Column(Integer, nullable=True, comment="实际导出行数")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="操作时间")
