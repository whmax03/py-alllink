"""
库存核心模型：warehouse / goods / sku_mapping / inventory

设计说明:
  1. warehouse  — 仓库主表（国内仓、各海外平台/国家仓库）
  2. goods      — 商品主表（代表一款真实的货，自建内部编码 G0001...）
  3. sku_mapping — SKU 映射表（一个商品 ↔ 多个仓库的不同 SKU）
  4. inventory  — 库存子表（关联仓库 + SKU + 库存数据，靠 warehouse_id 外键）
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import json
from app.database import Base


class Warehouse(Base):
    """
    仓库主表
    type: domestic（国内仓）/ overseas（海外仓）
    platform: 平台（ERP系统 / Shopee / Tiktok / eBay / 亚马逊）
    country: 国家
    code: 仓库编码（如 洁具成品仓库 / TH-BKK-03 / DE06）
    """
    __tablename__ = "warehouse"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="仓库名称")
    code = Column(String(100), index=True, nullable=True, comment="仓库编码")
    type = Column(String(20), nullable=False, comment="仓库类型: domestic/overseas")
    platform = Column(String(50), nullable=True, comment="平台: ERP/Shopee/Tiktok/eBay/亚马逊")
    country = Column(String(50), nullable=True, comment="国家")
    warehouse_type = Column(String(100), nullable=True, index=True, comment="数据来源文件名")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关联
    inventories = relationship("Inventory", back_populates="warehouse", cascade="all, delete-orphan")


class Goods(Base):
    """
    商品主表 — 代表一款真实的货
    internal_code: 自建唯一内部编码（G0001, G0002...）
    name: 商品名称（中文名）
    spec: 规格型号
    """
    __tablename__ = "goods"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    internal_code = Column(String(20), unique=True, index=True, nullable=False, comment="内部编码 G0001")
    name = Column(String(500), nullable=True, comment="商品名称")
    spec = Column(String(500), nullable=True, comment="规格型号")
    en_name = Column(String(500), nullable=True, comment="英文名称")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关联
    sku_mappings = relationship("SkuMapping", back_populates="goods", cascade="all, delete-orphan")


class SkuMapping(Base):
    """
    SKU 映射表 — 一个商品绑定多个仓库的不同 SKU
    goods_id → Goods.id
    warehouse_id → Warehouse.id
    sku: 该仓库系统里的 SKU 编码
    barcode: 条码
    """
    __tablename__ = "sku_mapping"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    goods_id = Column(Integer, ForeignKey("goods.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouse.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = Column(String(200), index=True, nullable=False, comment="该仓库的SKU编码")
    barcode = Column(String(200), nullable=True, comment="条码")
    product_code = Column(String(200), nullable=True, comment="产品代码/自定义编码")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关联
    goods = relationship("Goods", back_populates="sku_mappings")
    warehouse = relationship("Warehouse")


class Inventory(Base):
    """
    库存子表 — 关联仓库 + SKU + 库存数量
    warehouse_id → Warehouse.id
    sku_mapping_id → SkuMapping.id（可选，关联映射）
    sku: 该仓库的 SKU（冗余存储，方便查询）
    各仓库系统有不同的库存字段，这里统一存通用字段 + 原始数据 JSON
    """
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    warehouse_id = Column(Integer, ForeignKey("warehouse.id", ondelete="CASCADE"), nullable=False, index=True)
    sku_mapping_id = Column(Integer, ForeignKey("sku_mapping.id", ondelete="SET NULL"), nullable=True, index=True)

    # SKU 信息（冗余，方便直接查询）
    sku = Column(String(200), index=True, nullable=True, comment="SKU编码")
    name_cn = Column(String(500), nullable=True, comment="中文名称")
    name_en = Column(String(500), nullable=True, comment="英文名称")
    spec = Column(String(500), nullable=True, comment="规格")

    # 库存数据（通用字段）
    stock_qty = Column(Float, nullable=True, default=0, comment="库存数量/在库库存")
    available_qty = Column(Float, nullable=True, default=0, comment="可用库存")
    frozen_qty = Column(Float, nullable=True, default=0, comment="冻结数量")
    outbound_qty = Column(Float, nullable=True, default=0, comment="待出库数量")
    inbound_qty = Column(Float, nullable=True, default=0, comment="在途/待上架数量")

    # 入库ID列表（部分仓库如字米美国一个SKU对应多个入库批次）
    inbound_ids = Column(Text, nullable=True, comment="入库ID列表 JSON 数组")

    @property
    def inbound_id_list(self) -> list:
        """入库ID列表（自动解析 JSON 字符串为 list）"""
        if not self.inbound_ids:
            return []
        try:
            data = json.loads(self.inbound_ids)
            return data if isinstance(data, list) else []
        except (ValueError, TypeError):
            return []

    # 原始数据（存储各平台特有字段，方便追溯）
    raw_data = Column(Text, nullable=True, comment="原始Excel行数据 JSON")

    imported_at = Column(DateTime, default=datetime.utcnow, comment="导入时间")

    # 关联
    warehouse = relationship("Warehouse", back_populates="inventories")
