"""
库存 CRUD：warehouse / goods / sku_mapping / inventory 的数据库操作
"""
import json
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional, Tuple, Dict
from datetime import datetime

from app.models.inventory import Warehouse, Goods, SkuMapping, Inventory


# ========== 仓库 ==========

def get_or_create_warehouse(db: Session, name: str, code: str = None,
                            wh_type: str = "domestic", platform: str = None,
                            country: str = None, warehouse_type: str = None) -> Warehouse:
    """获取或创建仓库记录（按 name + type + warehouse_type 查找）"""
    wh = db.query(Warehouse).filter(
        Warehouse.name == name,
        Warehouse.type == wh_type,
        Warehouse.warehouse_type == warehouse_type if warehouse_type else Warehouse.warehouse_type.is_(None),
    ).first()
    if wh:
        return wh
    wh = Warehouse(
        name=name, code=code, type=wh_type,
        platform=platform, country=country,
        warehouse_type=warehouse_type,
    )
    db.add(wh)
    db.flush()
    return wh


def get_warehouses(db: Session, wh_type: Optional[str] = None) -> List[Warehouse]:
    query = db.query(Warehouse)
    if wh_type:
        query = query.filter(Warehouse.type == wh_type)
    return query.all()


# ========== 商品 ==========

def get_or_create_goods(db: Session, name: str, spec: str = None,
                        en_name: str = None) -> Goods:
    """获取或创建商品（按 name + spec 查找，自动生成内部编码）"""
    goods = db.query(Goods).filter(
        Goods.name == name,
        Goods.spec == (spec or "")
    ).first()
    if goods:
        return goods

    # 生成内部编码 G0001...
    count = db.query(Goods).count()
    internal_code = f"G{count + 1:04d}"

    goods = Goods(
        internal_code=internal_code,
        name=name, spec=spec, en_name=en_name,
    )
    db.add(goods)
    db.flush()
    return goods


def get_goods_list(db: Session, skip: int = 0, limit: int = 100) -> List[Goods]:
    return db.query(Goods).offset(skip).limit(limit).all()


# ========== SKU 映射 ==========

def get_or_create_sku_mapping(db: Session, goods_id: int, warehouse_id: int,
                              sku: str, barcode: str = None,
                              product_code: str = None) -> SkuMapping:
    """获取或创建 SKU 映射（按 goods_id + warehouse_id + sku 查找）"""
    mapping = db.query(SkuMapping).filter(
        SkuMapping.goods_id == goods_id,
        SkuMapping.warehouse_id == warehouse_id,
        SkuMapping.sku == sku,
    ).first()
    if mapping:
        return mapping
    mapping = SkuMapping(
        goods_id=goods_id, warehouse_id=warehouse_id,
        sku=sku, barcode=barcode, product_code=product_code,
    )
    db.add(mapping)
    db.flush()
    return mapping


# ========== 库存 ==========

def create_inventory_batch(db: Session, items: List[dict]) -> int:
    """批量插入库存数据，返回插入条数"""
    now = datetime.utcnow()
    db_items = [
        Inventory(
            warehouse_id=item["warehouse_id"],
            sku_mapping_id=item.get("sku_mapping_id"),
            sku=item.get("sku"),
            name_cn=item.get("name_cn"),
            name_en=item.get("name_en"),
            spec=item.get("spec"),
            stock_qty=item.get("stock_qty", 0),
            available_qty=item.get("available_qty", 0),
            frozen_qty=item.get("frozen_qty", 0),
            outbound_qty=item.get("outbound_qty", 0),
            inbound_qty=item.get("inbound_qty", 0),
            inbound_ids=json.dumps(item.get("inbound_ids"), ensure_ascii=False) if item.get("inbound_ids") else None,
            raw_data=json.dumps(item.get("raw_data"), ensure_ascii=False) if item.get("raw_data") else None,
            imported_at=now,
        )
        for item in items
    ]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)


def serialize_inventory(item: Inventory) -> Dict:
    """把 Inventory ORM 对象序列化为 dict，inbound_ids 自动转成 list"""
    d = {
        "id": item.id,
        "warehouse_id": item.warehouse_id,
        "sku_mapping_id": item.sku_mapping_id,
        "sku": item.sku,
        "name_cn": item.name_cn,
        "name_en": item.name_en,
        "spec": item.spec,
        "stock_qty": item.stock_qty,
        "available_qty": item.available_qty,
        "frozen_qty": item.frozen_qty,
        "outbound_qty": item.outbound_qty,
        "inbound_qty": item.inbound_qty,
        "inbound_ids": item.inbound_id_list,
        "raw_data": json.loads(item.raw_data) if item.raw_data else None,
        "imported_at": item.imported_at,
    }
    if item.warehouse:
        d["warehouse"] = {
            "id": item.warehouse.id,
            "name": item.warehouse.name,
            "code": item.warehouse.code,
            "type": item.warehouse.type,
            "platform": item.warehouse.platform,
            "country": item.warehouse.country,
            "warehouse_type": item.warehouse.warehouse_type,
            "created_at": item.warehouse.created_at,
        }
    else:
        d["warehouse"] = None
    return d


def get_inventory_page(db: Session, pageNo: int = 1, pageSize: int = 20,
                       sku: Optional[str] = None,
                       warehouse_id: Optional[int] = None,
                       wh_type: Optional[str] = None,
                       platform: Optional[str] = None,
                       country: Optional[str] = None,
                       warehouse_type: Optional[str] = None) -> Tuple[List[dict], int, float, int]:
    """
    分页查询库存。
    sku: 模糊搜索 SKU 或中英文名称
    warehouse_id: 按仓库筛选
    wh_type: 按仓库类型筛选（domestic/overseas）
    platform: 按平台筛选（eBay/Shopee/Tiktok/亚马逊/金蝶/ERP）
    country: 按国家筛选
    warehouse_type: 按数据来源文件名筛选（如 中邮英国/AU仓库/泰国 等）
    返回: (数据列表, 总条数, 库存数量总和, 去重仓库数)
    """
    query = db.query(Inventory).options(joinedload(Inventory.warehouse))

    # 需要 join Warehouse 的筛选条件
    needs_join = wh_type or platform or country or warehouse_type
    if needs_join:
        query = query.join(Warehouse)

    if sku:
        query = query.filter(
            Inventory.sku.ilike(f"%{sku}%") |
            Inventory.name_cn.ilike(f"%{sku}%") |
            Inventory.name_en.ilike(f"%{sku}%")
        )
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if wh_type:
        query = query.filter(Warehouse.type == wh_type)
    if platform:
        query = query.filter(Warehouse.platform == platform)
    if country:
        query = query.filter(Warehouse.country == country)
    if warehouse_type:
        query = query.filter(Warehouse.warehouse_type == warehouse_type)

    total = query.count()
    stock_sum = query.with_entities(func.coalesce(func.sum(Inventory.stock_qty), 0)).scalar()
    warehouse_count = query.with_entities(func.count(func.distinct(Inventory.warehouse_id))).scalar() or 0
    items = query.order_by(Inventory.id.desc()).offset((pageNo - 1) * pageSize).limit(pageSize).all()
    return [serialize_inventory(i) for i in items], total, float(stock_sum or 0), int(warehouse_count)


def delete_inventory_by_warehouse(db: Session, warehouse_id: int) -> int:
    """删除指定仓库的所有库存，返回删除条数"""
    count = db.query(Inventory).filter(Inventory.warehouse_id == warehouse_id).count()
    db.query(Inventory).filter(Inventory.warehouse_id == warehouse_id).delete()
    db.commit()
    return count


def delete_all_inventory(db: Session) -> int:
    """清空所有库存数据"""
    count = db.query(Inventory).count()
    db.query(Inventory).delete()
    db.commit()
    return count


# ========== 汇总 ==========

def get_inventory_summary(db: Session) -> dict:
    """库存汇总统计"""
    total_items = db.query(Inventory).count()
    total_stock = db.query(func.coalesce(func.sum(Inventory.stock_qty), 0)).scalar()
    total_warehouses = db.query(Warehouse).count()
    total_goods = db.query(Goods).count()
    domestic_count = db.query(Inventory).join(Warehouse).filter(Warehouse.type == "domestic").count()
    overseas_count = db.query(Inventory).join(Warehouse).filter(Warehouse.type == "overseas").count()
    return {
        "total_items": total_items,
        "total_stock": float(total_stock or 0),
        "total_warehouses": total_warehouses,
        "total_goods": total_goods,
        "domestic_count": domestic_count,
        "overseas_count": overseas_count,
    }


# ========== 批量导入（高性能） ==========

def batch_import(db: Session, data: Dict[str, list]) -> Dict[str, int]:
    """
    批量导入库存数据（高性能，使用内存缓存避免逐条查询）。
    data: {"domestic": [...], "overseas": [...]}

    每个 item 格式:
      {warehouse: {name, code, type, platform, country},
       sku, name_cn, name_en, spec, barcode, product_code,
       stock_qty, available_qty, frozen_qty, outbound_qty, inbound_qty,
       raw_data}
    """
    now = datetime.utcnow()

    # 预加载缓存
    warehouse_cache = {}  # (name, type, warehouse_type) -> Warehouse
    for wh in db.query(Warehouse).all():
        warehouse_cache[(wh.name, wh.type, wh.warehouse_type)] = wh

    goods_cache = {}  # (name, spec or "") -> Goods
    for g in db.query(Goods).all():
        goods_cache[(g.name, g.spec or "")] = g

    sku_cache = {}  # (goods_id, warehouse_id, sku) -> SkuMapping
    for sm in db.query(SkuMapping).all():
        sku_cache[(sm.goods_id, sm.warehouse_id, sm.sku)] = sm

    goods_counter = db.query(Goods).count()

    inventory_rows = []

    for wh_type in ["domestic", "overseas"]:
        items = data.get(wh_type, [])
        for item in items:
            wh_info = item.get("warehouse", {})
            wh_name = wh_info.get("name", "")
            cache_key = (wh_name, wh_info.get("type", wh_type), wh_info.get("warehouse_type"))

            # 仓库缓存
            if cache_key not in warehouse_cache:
                wh = Warehouse(
                    name=wh_name,
                    code=wh_info.get("code"),
                    type=wh_info.get("type", wh_type),
                    platform=wh_info.get("platform"),
                    country=wh_info.get("country"),
                    warehouse_type=wh_info.get("warehouse_type"),
                )
                db.add(wh)
                db.flush()
                warehouse_cache[cache_key] = wh
            else:
                wh = warehouse_cache[cache_key]

            # 商品缓存
            goods_name = item.get("name_cn") or item.get("name_en") or item.get("sku") or ""
            goods_spec = item.get("spec") or ""
            g_cache_key = (goods_name, goods_spec)

            if g_cache_key not in goods_cache:
                goods_counter += 1
                internal_code = f"G{goods_counter:04d}"
                goods = Goods(
                    internal_code=internal_code,
                    name=goods_name,
                    spec=goods_spec or None,
                    en_name=item.get("name_en"),
                )
                db.add(goods)
                db.flush()
                goods_cache[g_cache_key] = goods
            else:
                goods = goods_cache[g_cache_key]

            # SKU 映射缓存
            sku_val = item.get("sku", "")
            mapping_id = None
            if sku_val:
                sm_key = (goods.id, wh.id, sku_val)
                if sm_key not in sku_cache:
                    mapping = SkuMapping(
                        goods_id=goods.id,
                        warehouse_id=wh.id,
                        sku=sku_val,
                        barcode=item.get("barcode"),
                        product_code=item.get("product_code"),
                    )
                    db.add(mapping)
                    db.flush()
                    sku_cache[sm_key] = mapping
                mapping_id = sku_cache[sm_key].id

            inventory_rows.append({
                "warehouse_id": wh.id,
                "sku_mapping_id": mapping_id,
                "sku": sku_val,
                "name_cn": item.get("name_cn"),
                "name_en": item.get("name_en"),
                "spec": item.get("spec"),
                "stock_qty": item.get("stock_qty", 0),
                "available_qty": item.get("available_qty", 0),
                "frozen_qty": item.get("frozen_qty", 0),
                "outbound_qty": item.get("outbound_qty", 0),
                "inbound_qty": item.get("inbound_qty", 0),
                "inbound_ids": json.dumps(item.get("inbound_ids"), ensure_ascii=False) if item.get("inbound_ids") else None,
                "raw_data": json.dumps(item.get("raw_data"), ensure_ascii=False) if item.get("raw_data") else None,
                "imported_at": now,
            })

    # 批量插入库存
    db.bulk_insert_mappings(Inventory, inventory_rows)
    db.commit()

    return {
        "total": len(inventory_rows),
        "warehouses": len(warehouse_cache),
        "goods": len(goods_cache),
        "sku_mappings": len(sku_cache),
    }
