from sqlalchemy.orm import Session
from typing import List, Optional, Tuple
from datetime import datetime

from app.models.inventory import DomesticInventory, OverseasInventory


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
                      sku: Optional[str] = None) -> Tuple[List[DomesticInventory], int]:
    """
    分页查询国内仓库存。
    sku: 模糊搜索物料编码(material_code)或物料名称(material_name)
    返回: (数据列表, 总条数)
    """
    query = db.query(DomesticInventory)
    if sku:
        query = query.filter(
            DomesticInventory.material_code.ilike(f"%{sku}%") |
            DomesticInventory.material_name.ilike(f"%{sku}%")
        )
    total = query.count()
    items = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    return items, total


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
                      sku: Optional[str] = None) -> Tuple[List[OverseasInventory], int]:
    """
    分页查询海外仓库存。
    sku: 模糊搜索 sku 或中英文品名
    返回: (数据列表, 总条数)
    """
    query = db.query(OverseasInventory)
    if sku:
        query = query.filter(
            OverseasInventory.sku.ilike(f"%{sku}%") |
            OverseasInventory.cn_name.ilike(f"%{sku}%") |
            OverseasInventory.en_name.ilike(f"%{sku}%")
        )
    total = query.count()
    items = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    return items, total


def get_overseas_count(db: Session) -> int:
    return db.query(OverseasInventory).count()


def delete_overseas_all(db: Session) -> int:
    """清空海外仓表，返回删除条数"""
    count = db.query(OverseasInventory).count()
    db.query(OverseasInventory).delete()
    db.commit()
    return count
