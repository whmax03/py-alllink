from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.core.excel_reader import read_domestic_inventory, read_overseas_inventory
from app.crud import inventory as crud_inventory
from app.schemas.inventory import (
    DomesticInventoryResponse,
    OverseasInventoryResponse,
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
    """一键导入国内仓和海外仓库存数据"""
    results = []
    for warehouse_type, read_fn, import_fn in [
        ("国内仓", read_domestic_inventory, crud_inventory.create_domestic_batch),
        ("海外仓", read_overseas_inventory, crud_inventory.create_overseas_batch),
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

    return results


# ========== 查询接口 ==========

@router.get("/domestic", summary="分页查询国内仓库存")
def list_domestic(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索物料编码或物料名称"),
    db: Session = Depends(get_db),
):
    """分页查询国内仓库存，返回 list + total"""
    items, total = crud_inventory.get_domestic_page(db, pageNo=pageNo, pageSize=pageSize, sku=sku)
    return {"list": items, "total": total, "pageNo": pageNo, "pageSize": pageSize}


@router.get("/overseas", summary="分页查询海外仓库存")
def list_overseas(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或中英文品名"),
    db: Session = Depends(get_db),
):
    """分页查询海外仓库存，返回 list + total"""
    items, total = crud_inventory.get_overseas_page(db, pageNo=pageNo, pageSize=pageSize, sku=sku)
    return {"list": items, "total": total, "pageNo": pageNo, "pageSize": pageSize}
