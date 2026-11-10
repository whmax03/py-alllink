from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Tuple
from datetime import datetime

from app.models.inventory import (
    DomesticInventory, OverseasInventory,
    OverseasTransitInventory, OverseasTransitDetail,
)


# ========== 国内仓 ==========

def create_domestic_batch(db: Session, items: List[dict]) -> int:
    """批量插入国内仓库存数据，返回插入条数"""
    now = datetime.utcnow()
    db_items = [
        DomesticInventory(
            material_code=item.get("material_code"),
            material_name=item.get("material_name"),
            spec_model=item.get("spec_model"),
            plan_tracking_no=item.get("plan_tracking_no"),
            warehouse_name=item.get("warehouse_name"),
            stock_unit=item.get("stock_unit"),
            stock_qty=item.get("stock_qty"),
            imported_at=now,
        )
        for item in items
    ]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)


def get_domestic_page(db: Session, pageNo: int = 1, pageSize: int = 20,
                      sku: Optional[str] = None) -> Tuple[List[DomesticInventory], int, float]:
    """
    分页查询国内仓库存。
    sku: 模糊搜索物料编码(material_code)或物料名称(material_name)
    返回: (数据列表, 总条数, 库存量总和)
    """
    query = db.query(DomesticInventory)
    if sku:
        query = query.filter(
            DomesticInventory.material_code.ilike(f"%{sku}%") |
            DomesticInventory.material_name.ilike(f"%{sku}%")
        )
    total = query.count()
    stock_sum = query.with_entities(func.coalesce(func.sum(DomesticInventory.stock_qty), 0)).scalar()
    items = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    return items, total, float(stock_sum or 0)


def get_domestic_count(db: Session) -> int:
    return db.query(DomesticInventory).count()


def delete_domestic_all(db: Session) -> int:
    """清空国内仓表，返回删除条数"""
    count = db.query(DomesticInventory).count()
    db.query(DomesticInventory).delete()
    db.commit()
    return count


# ========== 海外仓 ==========

def create_overseas_batch(db: Session, items: List[dict]) -> int:
    """批量插入海外仓库存数据，返回插入条数"""
    now = datetime.utcnow()
    db_items = [
        OverseasInventory(
            customer=item.get("customer"),
            sku=item.get("sku"),
            country_warehouse=item.get("country_warehouse"),
            cn_name=item.get("cn_name"),
            en_name=item.get("en_name"),
            total_stock=item.get("total_stock"),
            outbound_info=item.get("outbound_info"),
            inbound_id=item.get("inbound_id"),
            stock=item.get("stock"),
            inbound_date=item.get("inbound_date"),
            storage_days=item.get("storage_days"),
            imported_at=now,
        )
        for item in items
    ]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)


def get_overseas_page(db: Session, pageNo: int = 1, pageSize: int = 20,
                      sku: Optional[str] = None) -> Tuple[List[OverseasInventory], int, float]:
    """
    分页查询海外仓库存。
    sku: 模糊搜索 sku 或中英文品名
    返回: (数据列表, 总条数, 库存总数总和)
    """
    query = db.query(OverseasInventory)
    if sku:
        query = query.filter(
            OverseasInventory.sku.ilike(f"%{sku}%") |
            OverseasInventory.cn_name.ilike(f"%{sku}%") |
            OverseasInventory.en_name.ilike(f"%{sku}%")
        )
    total = query.count()
    stock_sum = query.with_entities(func.coalesce(func.sum(OverseasInventory.total_stock), 0)).scalar()
    items = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    return items, total, float(stock_sum or 0)


def get_overseas_count(db: Session) -> int:
    return db.query(OverseasInventory).count()


def delete_overseas_all(db: Session) -> int:
    """清空海外仓表，返回删除条数"""
    count = db.query(OverseasInventory).count()
    db.query(OverseasInventory).delete()
    db.commit()
    return count


# ========== 海外仓转运 — 库存信息 ==========

def create_transit_inventory_batch(db: Session, items: List[dict]) -> int:
    """批量插入转运库存信息，返回插入条数"""
    now = datetime.utcnow()
    db_items = [
        OverseasTransitInventory(
            customer=item.get("customer"),
            sku=item.get("sku"),
            box_mark_no=item.get("box_mark_no"),
            stock_qty=item.get("stock_qty"),
            stock=item.get("stock"),
            frozen=item.get("frozen"),
            country=item.get("country"),
            warehouse=item.get("warehouse"),
            shelf=item.get("shelf"),
            imported_at=now,
        )
        for item in items
    ]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)


def get_transit_inventory_page(db: Session, pageNo: int = 1, pageSize: int = 20,
                               sku: Optional[str] = None) -> Tuple[List[OverseasTransitInventory], int, int]:
    """分页查询转运库存信息，sku 模糊搜索 sku 或箱唛号
    返回: (数据列表, 总条数, 库存总和)
    """
    query = db.query(OverseasTransitInventory)
    if sku:
        query = query.filter(
            OverseasTransitInventory.sku.ilike(f"%{sku}%") |
            OverseasTransitInventory.box_mark_no.ilike(f"%{sku}%")
        )
    total = query.count()
    stock_sum = query.with_entities(func.coalesce(func.sum(OverseasTransitInventory.stock), 0)).scalar()
    items = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    return items, total, int(stock_sum or 0)


def delete_transit_inventory_all(db: Session) -> int:
    count = db.query(OverseasTransitInventory).count()
    db.query(OverseasTransitInventory).delete()
    db.commit()
    return count


# ========== 海外仓转运 — 库存明细 ==========

def create_transit_detail_batch(db: Session, items: List[dict]) -> int:
    """批量插入转运库存明细，返回插入条数"""
    now = datetime.utcnow()
    db_items = [
        OverseasTransitDetail(
            inbound_id=item.get("inbound_id"),
            box_mark_no=item.get("box_mark_no"),
            sku=item.get("sku"),
            product_qty=item.get("product_qty"),
            product_code=item.get("product_code"),
            status=item.get("status"),
            shelf=item.get("shelf"),
            inbound_date=item.get("inbound_date"),
            storage_days=item.get("storage_days"),
            imported_at=now,
        )
        for item in items
    ]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)


def get_transit_detail_page(db: Session, pageNo: int = 1, pageSize: int = 20,
                            sku: Optional[str] = None) -> Tuple[List[OverseasTransitDetail], int, int]:
    """分页查询转运库存明细，sku 模糊搜索 sku 或箱唛号
    返回: (数据列表, 总条数, 产品数量总和)
    """
    query = db.query(OverseasTransitDetail)
    if sku:
        query = query.filter(
            OverseasTransitDetail.sku.ilike(f"%{sku}%") |
            OverseasTransitDetail.box_mark_no.ilike(f"%{sku}%")
        )
    total = query.count()
    qty_sum = query.with_entities(func.coalesce(func.sum(OverseasTransitDetail.product_qty), 0)).scalar()
    items = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    return items, total, int(qty_sum or 0)


def delete_transit_detail_all(db: Session) -> int:
    count = db.query(OverseasTransitDetail).count()
    db.query(OverseasTransitDetail).delete()
    db.commit()
    return count
