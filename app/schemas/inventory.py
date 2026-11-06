from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Generic, TypeVar


# ========== 分页响应模型 ==========

T = TypeVar("T")

class PageResponse(BaseModel, Generic[T]):
    """通用分页响应结构"""
    list: List[T]
    total: int
    pageNo: int
    pageSize: int


# ========== 国内仓 ==========

class DomesticInventoryBase(BaseModel):
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    spec_model: Optional[str] = None
    plan_tracking_no: Optional[str] = None
    warehouse_name: Optional[str] = None
    stock_unit: Optional[str] = None
    stock_qty: Optional[float] = None


class DomesticInventoryResponse(DomesticInventoryBase):
    id: int
    imported_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========== 海外仓 ==========

class OverseasInventoryBase(BaseModel):
    customer: Optional[str] = None
    sku: Optional[str] = None
    country_warehouse: Optional[str] = None
    cn_name: Optional[str] = None
    en_name: Optional[str] = None
    total_stock: Optional[float] = None
    outbound_info: Optional[str] = None
    inbound_id: Optional[str] = None
    stock: Optional[str] = None
    inbound_date: Optional[str] = None
    storage_days: Optional[int] = None


class OverseasInventoryResponse(OverseasInventoryBase):
    id: int
    imported_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========== 导入结果 ==========

class ImportResult(BaseModel):
    warehouse_type: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    message: str
