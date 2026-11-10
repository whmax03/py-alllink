from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.core.excel_reader import (
    read_domestic_inventory, read_overseas_inventory,
    read_overseas_transit_inventory,
)
from app.crud import inventory as crud_inventory
from app.schemas.inventory import (
    DomesticInventoryResponse,
    OverseasInventoryResponse,
    OverseasTransitInventoryResponse,
    OverseasTransitDetailResponse,
    ImportResult,
    PageResponse,
)

router = APIRouter(prefix="/inventory", tags=["库存管理"])


# ========== 导入接口 ==========

@router.post("/domestic/import", summary="导入国内仓库存")
def import_domestic(db: Session = Depends(get_db)):
    """从 Excel 文件读取国内仓库存数据并写入数据库，每次导入前先清空旧数据"""
    try:
        items = read_domestic_inventory()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Excel失败: {str(e)}")

    deleted = crud_inventory.delete_domestic_all(db)
    imported = crud_inventory.create_domestic_batch(db, items)

    return ImportResult(
        warehouse_type="国内仓",
        total_rows=len(items),
        imported_rows=imported,
        skipped_rows=0,
        message=f"成功导入 {imported} 条数据（已清除旧数据 {deleted} 条）",
    )


@router.post("/overseas/import", summary="导入海外仓库存")
def import_overseas(db: Session = Depends(get_db)):
    """从 Excel 文件读取海外仓库存数据并写入数据库，每次导入前先清空旧数据"""
    try:
        items = read_overseas_inventory()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Excel失败: {str(e)}")

    deleted = crud_inventory.delete_overseas_all(db)
    imported = crud_inventory.create_overseas_batch(db, items)

    return ImportResult(
        warehouse_type="海外仓",
        total_rows=len(items),
        imported_rows=imported,
        skipped_rows=0,
        message=f"成功导入 {imported} 条数据（已清除旧数据 {deleted} 条）",
    )


@router.post("/import-all", summary="一键导入全部库存")
def import_all(db: Session = Depends(get_db)):
    """一键导入国内仓、海外仓一件代发、海外仓转运库存数据"""
    results = []
    for warehouse_type, read_fn, import_fn in [
        ("国内仓", read_domestic_inventory, crud_inventory.create_domestic_batch),
        ("海外仓-一件代发", read_overseas_inventory, crud_inventory.create_overseas_batch),
    ]:
        try:
            items = read_fn()
        except FileNotFoundError as e:
            results.append(ImportResult(
                warehouse_type=warehouse_type, total_rows=0,
                imported_rows=0, skipped_rows=0, message=f"文件不存在: {e}",
            ))
            continue
        except Exception as e:
            results.append(ImportResult(
                warehouse_type=warehouse_type, total_rows=0,
                imported_rows=0, skipped_rows=0, message=f"读取失败: {e}",
            ))
            continue

        imported = import_fn(db, items)
        results.append(ImportResult(
            warehouse_type=warehouse_type,
            total_rows=len(items),
            imported_rows=imported,
            skipped_rows=0,
            message=f"成功导入 {imported} 条数据",
        ))

    # 转运库存（两个 Sheet 一起导入）
    try:
        inv_data, detail_data = read_overseas_transit_inventory()
        # 库存信息
        crud_inventory.delete_transit_inventory_all(db)
        inv_imported = crud_inventory.create_transit_inventory_batch(db, inv_data)
        results.append(ImportResult(
            warehouse_type="海外仓-转运库存信息",
            total_rows=len(inv_data),
            imported_rows=inv_imported,
            skipped_rows=0,
            message=f"成功导入 {inv_imported} 条数据",
        ))
        # 库存明细
        crud_inventory.delete_transit_detail_all(db)
        detail_imported = crud_inventory.create_transit_detail_batch(db, detail_data)
        results.append(ImportResult(
            warehouse_type="海外仓-转运库存明细",
            total_rows=len(detail_data),
            imported_rows=detail_imported,
            skipped_rows=0,
            message=f"成功导入 {detail_imported} 条数据",
        ))
    except FileNotFoundError as e:
        results.append(ImportResult(
            warehouse_type="海外仓-转运", total_rows=0,
            imported_rows=0, skipped_rows=0, message=f"文件不存在: {e}",
        ))
    except Exception as e:
        results.append(ImportResult(
            warehouse_type="海外仓-转运", total_rows=0,
            imported_rows=0, skipped_rows=0, message=f"读取失败: {e}",
        ))

    return results


# ========== 查询接口 ==========

@router.get("/domestic", summary="分页查询国内仓库存")
def list_domestic(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索物料编码或物料名称"),
    db: Session = Depends(get_db),
):
    """分页查询国内仓库存，返回 list + total + totalStock（库存量总和）"""
    items, total, stock_sum = crud_inventory.get_domestic_page(db, pageNo=pageNo, pageSize=pageSize, sku=sku)
    return {"list": items, "total": total, "totalStock": stock_sum, "pageNo": pageNo, "pageSize": pageSize}


@router.get("/overseas", summary="分页查询海外仓库存")
def list_overseas(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或中英文品名"),
    db: Session = Depends(get_db),
):
    """分页查询海外仓库存，返回 list + total + totalStock（库存总数总和）"""
    items, total, stock_sum = crud_inventory.get_overseas_page(db, pageNo=pageNo, pageSize=pageSize, sku=sku)
    return {"list": items, "total": total, "totalStock": stock_sum, "pageNo": pageNo, "pageSize": pageSize}


# ========== 海外仓转运 — 导入接口 ==========

@router.post("/transit/import", summary="导入海外仓转运库存")
def import_transit(db: Session = Depends(get_db)):
    """
    从 字米_转运.xlsx 读取两个 Sheet 并写入数据库，每次导入前先清空旧数据。
    Sheet1「库存信息」→ overseas_transit_inventory 表
    Sheet2「库存明细信息」→ overseas_transit_detail 表
    """
    try:
        inv_data, detail_data = read_overseas_transit_inventory()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Excel失败: {str(e)}")

    # 库存信息
    deleted_inv = crud_inventory.delete_transit_inventory_all(db)
    imported_inv = crud_inventory.create_transit_inventory_batch(db, inv_data)

    # 库存明细
    deleted_detail = crud_inventory.delete_transit_detail_all(db)
    imported_detail = crud_inventory.create_transit_detail_batch(db, detail_data)

    return {
        "库存信息": ImportResult(
            warehouse_type="海外仓-转运库存信息",
            total_rows=len(inv_data),
            imported_rows=imported_inv,
            skipped_rows=0,
            message=f"成功导入 {imported_inv} 条数据（已清除旧数据 {deleted_inv} 条）",
        ),
        "库存明细": ImportResult(
            warehouse_type="海外仓-转运库存明细",
            total_rows=len(detail_data),
            imported_rows=imported_detail,
            skipped_rows=0,
            message=f"成功导入 {imported_detail} 条数据（已清除旧数据 {deleted_detail} 条）",
        ),
    }


# ========== 海外仓转运 — 查询接口 ==========

@router.get("/transit/inventory", summary="分页查询转运库存信息")
def list_transit_inventory(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或箱唛号"),
    db: Session = Depends(get_db),
):
    """分页查询转运库存信息，返回 list + total + totalStock（库存总和）"""
    items, total, stock_sum = crud_inventory.get_transit_inventory_page(db, pageNo=pageNo, pageSize=pageSize, sku=sku)
    return {"list": items, "total": total, "totalStock": stock_sum, "pageNo": pageNo, "pageSize": pageSize}


@router.get("/transit/detail", summary="分页查询转运库存明细")
def list_transit_detail(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或箱唛号"),
    db: Session = Depends(get_db),
):
    """分页查询转运库存明细，返回 list + total + totalStock（产品数量总和）"""
    items, total, qty_sum = crud_inventory.get_transit_detail_page(db, pageNo=pageNo, pageSize=pageSize, sku=sku)
    return {"list": items, "total": total, "totalStock": qty_sum, "pageNo": pageNo, "pageSize": pageSize}
