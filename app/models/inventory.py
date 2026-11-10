from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from datetime import datetime
from app.database import Base


class DomesticInventory(Base):
    """国内仓库存表"""
    __tablename__ = "domestic_inventory"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    material_code = Column(String(100), index=True, nullable=True, comment="物料编码")
    material_name = Column(String(500), nullable=True, comment="物料名称")
    spec_model = Column(String(500), nullable=True, comment="规格型号")
    plan_tracking_no = Column(String(100), nullable=True, comment="计划跟踪号")
    warehouse_name = Column(String(200), nullable=True, comment="仓库名称")
    stock_unit = Column(String(50), nullable=True, comment="库存主单位")
    stock_qty = Column(Float, nullable=True, comment="库存量(主单位)")
    imported_at = Column(DateTime, default=datetime.utcnow, comment="导入时间")


class OverseasInventory(Base):
    """海外仓库存表 — 对应 字米_一件代发库存.xlsx"""
    __tablename__ = "overseas_inventory"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer = Column(String(100), nullable=True, comment="客户")
    sku = Column(String(200), index=True, nullable=True, comment="SKU")
    country_warehouse = Column(String(200), nullable=True, comment="国家(仓库)")
    cn_name = Column(String(500), nullable=True, comment="中文品名")
    en_name = Column(String(500), nullable=True, comment="英文品名")
    total_stock = Column(Float, nullable=True, comment="库存总数")
    outbound_info = Column(String(200), nullable=True, comment="出库(已出库/出库数/冻结数)")
    inbound_id = Column(String(100), nullable=True, comment="入库ID")
    stock = Column(String(100), nullable=True, comment="库存")
    inbound_date = Column(String(50), nullable=True, comment="入库时间")
    storage_days = Column(Integer, nullable=True, comment="存放天数")
    imported_at = Column(DateTime, default=datetime.utcnow, comment="导入时间")


class OverseasTransitInventory(Base):
    """海外仓转运库存信息表 — 对应 字米_转运.xlsx Sheet1「库存信息」"""
    __tablename__ = "overseas_transit_inventory"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer = Column(String(100), nullable=True, comment="客户")
    sku = Column(String(200), index=True, nullable=True, comment="SKU")
    box_mark_no = Column(String(200), nullable=True, comment="箱唛号")
    stock_qty = Column(Integer, nullable=True, comment="库存数量")
    stock = Column(Integer, nullable=True, comment="库存")
    frozen = Column(Integer, nullable=True, comment="冻结")
    country = Column(String(100), nullable=True, comment="国家")
    warehouse = Column(String(200), nullable=True, comment="仓库")
    shelf = Column(String(100), nullable=True, comment="货架")
    imported_at = Column(DateTime, default=datetime.utcnow, comment="导入时间")


class OverseasTransitDetail(Base):
    """海外仓转运库存明细表 — 对应 字米_转运.xlsx Sheet2「库存明细信息」"""
    __tablename__ = "overseas_transit_detail"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    inbound_id = Column(String(100), index=True, nullable=True, comment="入库ID")
    box_mark_no = Column(String(200), nullable=True, comment="箱唛号")
    sku = Column(String(200), index=True, nullable=True, comment="SKU")
    product_qty = Column(Integer, nullable=True, comment="产品数量")
    product_code = Column(String(200), nullable=True, comment="产品代码")
    status = Column(String(100), nullable=True, comment="状态")
    shelf = Column(String(100), nullable=True, comment="货架")
    inbound_date = Column(String(50), nullable=True, comment="入库时间")
    storage_days = Column(Integer, nullable=True, comment="存放天数")
    imported_at = Column(DateTime, default=datetime.utcnow, comment="导入时间")
