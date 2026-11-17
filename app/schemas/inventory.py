"""
库存 Schema：仓库/商品/SKU映射/库存 的请求和响应模型
"""
import json
from pydantic import BaseModel, model_validator
from datetime import datetime
from typing import Optional, List, TypeVar, Generic

T = TypeVar("T")


# ---------- 仓库 ----------

class WarehouseResponse(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    type: str
    platform: Optional[str] = None
    country: Optional[str] = None
    warehouse_type: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- 商品 ----------

class GoodsResponse(BaseModel):
    id: int
    internal_code: str
    name: Optional[str] = None
    spec: Optional[str] = None
    en_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- SKU 映射 ----------

class SkuMappingResponse(BaseModel):
    id: int
    goods_id: int
    warehouse_id: int
    sku: str
    barcode: Optional[str] = None
    product_code: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- 库存 ----------

class InventoryResponse(BaseModel):
    id: int
    warehouse_id: int
    sku_mapping_id: Optional[int] = None
    sku: Optional[str] = None
    name_cn: Optional[str] = None
    name_en: Optional[str] = None
    spec: Optional[str] = None
    stock_qty: Optional[float] = 0
    available_qty: Optional[float] = 0
    frozen_qty: Optional[float] = 0
    outbound_qty: Optional[float] = 0
    inbound_qty: Optional[float] = 0
    inbound_ids: Optional[List[str]] = None
    imported_at: Optional[datetime] = None
    warehouse: Optional[WarehouseResponse] = None

    class Config:
        from_attributes = True

    @classmethod
    def _parse_inbound_ids(cls, v):
        """inbound_ids 在库里是 JSON 字符串，转成 list"""
        if v is None or v == "":
            return None
        if isinstance(v, list):
            return v
        try:
            data = json.loads(v)
            return data if isinstance(data, list) else None
        except (ValueError, TypeError):
            return None

    @model_validator(mode="before")
    @classmethod
    def _handle_inbound_ids(cls, data):
        if isinstance(data, dict) and "inbound_ids" in data:
            data = dict(data)
            data["inbound_ids"] = cls._parse_inbound_ids(data["inbound_ids"])
        return data


# ---------- 分页响应 ----------

class PageResponse(BaseModel, Generic[T]):
    list: List[T]
    total: int
    totalStock: float
    pageNo: int
    pageSize: int


# ---------- 导入结果 ----------

class ImportResult(BaseModel):
    warehouse_type: str
    total_rows: int = 0
    imported_rows: int = 0
    skipped_rows: int = 0
    message: str = ""
