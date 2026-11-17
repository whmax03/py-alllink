"""
库存路由：导入 / 查询 / 汇总
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.core.excel_reader import read_all_inventory
from app.crud import inventory as crud_inventory
from app.schemas.inventory import ImportResult

router = APIRouter(prefix="/inventory", tags=["库存管理"])


# ========== 导入接口 ==========

@router.post("/import-all", summary="一键导入全部库存")
def import_all(db: Session = Depends(get_db)):
    """
    一键读取 ERP 数据源目录下所有 Excel 文件并导入。
    自动创建仓库记录、商品记录、SKU 映射、库存记录。
    每次导入前清空旧库存数据（保留仓库/商品/SKU映射）。
    """
    try:
        data = read_all_inventory()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Excel失败: {str(e)}")

    # 清空旧库存
    deleted = crud_inventory.delete_all_inventory(db)

    # 批量导入
    stats = crud_inventory.batch_import(db, data)

    return {
        "deleted_old": deleted,
        "imported": stats["total"],
        "warehouses": stats["warehouses"],
        "goods": stats["goods"],
        "sku_mappings": stats["sku_mappings"],
        "message": f"成功导入 {stats['total']} 条库存（仓库 {stats['warehouses']} 个，商品 {stats['goods']} 个）",
    }


@router.post("/import/domestic", summary="仅导入国内仓库存")
def import_domestic(db: Session = Depends(get_db)):
    """仅导入国内仓数据"""
    from app.core.excel_reader import read_domestic_inventory
    try:
        items = read_domestic_inventory()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Excel失败: {str(e)}")

    inventory_rows = []
    for item in items:
        wh_info = item.get("warehouse", {})
        wh = crud_inventory.get_or_create_warehouse(
            db, name=wh_info.get("name", ""), code=wh_info.get("code"),
            wh_type="domestic", platform=wh_info.get("platform"),
            country=wh_info.get("country"),
            warehouse_type=wh_info.get("warehouse_type"),
        )
        goods = crud_inventory.get_or_create_goods(
            db, name=item.get("name_cn") or item.get("sku") or "",
            spec=item.get("spec"), en_name=item.get("name_en"),
        )
        sku_val = item.get("sku", "")
        mapping_id = None
        if sku_val:
            mapping = crud_inventory.get_or_create_sku_mapping(
                db, goods_id=goods.id, warehouse_id=wh.id, sku=sku_val,
            )
            mapping_id = mapping.id
        inventory_rows.append({
            "warehouse_id": wh.id, "sku_mapping_id": mapping_id,
            "sku": sku_val, "name_cn": item.get("name_cn"),
            "name_en": item.get("name_en"), "spec": item.get("spec"),
            "stock_qty": item.get("stock_qty", 0),
            "available_qty": item.get("available_qty", 0),
            "frozen_qty": item.get("frozen_qty", 0),
            "outbound_qty": item.get("outbound_qty", 0),
            "inbound_qty": item.get("inbound_qty", 0),
            "raw_data": item.get("raw_data"),
        })

    imported = crud_inventory.create_inventory_batch(db, inventory_rows)
    return ImportResult(
        warehouse_type="国内仓", total_rows=len(items),
        imported_rows=imported, skipped_rows=0,
        message=f"成功导入 {imported} 条",
    )


# ========== 查询接口 ==========

@router.get("/list", summary="分页查询库存")
def list_inventory(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或名称"),
    warehouse_id: Optional[int] = Query(None, description="按仓库ID筛选"),
    wh_type: Optional[str] = Query(None, description="按仓库类型筛选: domestic/overseas"),
    db: Session = Depends(get_db),
):
    """分页查询库存，返回 list + total + totalStock + warehouseCount"""
    items, total, stock_sum, wh_count = crud_inventory.get_inventory_page(
        db, pageNo=pageNo, pageSize=pageSize, sku=sku,
        warehouse_id=warehouse_id, wh_type=wh_type,
    )
    return {
        "list": items,
        "total": total,
        "totalStock": stock_sum,
        "warehouseCount": wh_count,
        "pageNo": pageNo,
        "pageSize": pageSize,
    }


@router.get("/domestic", summary="分页查询国内仓库存")
def list_domestic(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=500),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或名称"),
    db: Session = Depends(get_db),
):
    """分页查询国内仓库存"""
    items, total, stock_sum, wh_count = crud_inventory.get_inventory_page(
        db, pageNo=pageNo, pageSize=pageSize, sku=sku, wh_type="domestic",
    )
    return {"list": items, "total": total, "totalStock": stock_sum,
            "warehouseCount": wh_count,
            "pageNo": pageNo, "pageSize": pageSize}


@router.get("/overseas", summary="分页查询海外仓库存")
def list_overseas(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=500),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或名称"),
    platform: Optional[str] = Query(None, description="按平台筛选: eBay/Shopee/Tiktok/亚马逊"),
    country: Optional[str] = Query(None, description="按国家筛选: 泰国/马来西亚/英国 等"),
    warehouse_type: Optional[str] = Query(None, description="按数据来源文件名筛选: 中邮英国/AU仓库/泰国 等"),
    db: Session = Depends(get_db),
):
    """
    分页查询海外仓库存，支持以下筛选方式（可组合）：
    - platform + country: 按平台和国家组合筛选
    - warehouse_type: 按数据来源文件名筛选（如 "中邮英国" 对应 海外仓/亚马逊/中邮英国.xlsx）
    - sku: 模糊搜索SKU或名称
    """
    items, total, stock_sum, wh_count = crud_inventory.get_inventory_page(
        db, pageNo=pageNo, pageSize=pageSize, sku=sku,
        wh_type="overseas", platform=platform, country=country,
        warehouse_type=warehouse_type,
    )
    return {"list": items, "total": total, "totalStock": stock_sum,
            "warehouseCount": wh_count,
            "pageNo": pageNo, "pageSize": pageSize}


# ========== 仓库列表 ==========

@router.get("/warehouses", summary="获取仓库列表")
def list_warehouses(
    wh_type: Optional[str] = Query(None, description="按类型筛选: domestic/overseas"),
    db: Session = Depends(get_db),
):
    """获取仓库列表"""
    return crud_inventory.get_warehouses(db, wh_type=wh_type)


# ========== 商品列表 ==========

@router.get("/goods", summary="获取商品列表")
def list_goods(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """获取商品列表"""
    return crud_inventory.get_goods_list(db, skip=skip, limit=limit)


# ========== 汇总 ==========

@router.get("/summary", summary="库存汇总统计")
def inventory_summary(db: Session = Depends(get_db)):
    """库存汇总：总条数、总库存、仓库数、商品数、国内/海外分别多少"""
    return crud_inventory.get_inventory_summary(db)
