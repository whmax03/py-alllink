"""
库存路由：导入 / 查询 / 汇总
所有接口均需 JWT 登录，导入类接口额外需要 data:import 权限。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.core.excel_reader import read_all_inventory
from app.core.security import get_current_user, require_permission
from app.crud import inventory as crud_inventory
from app.crud import rbac as crud_rbac
from app.schemas.inventory import ImportResult
from app.models.user import User
from app.core.owner_backfill import refresh_owner_map, apply_owner_backfill

router = APIRouter(prefix="/inventory", tags=["库存管理"])


# ========== 导入接口 ==========

@router.post("/import-all", summary="一键导入全部库存")
def import_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("data:import")),
):
    """
    一键读取 ERP 数据源目录下所有 Excel 文件并导入。
    自动创建仓库记录、商品记录、SKU 映射、库存记录。
    每次导入前清空旧库存数据（保留仓库/商品/SKU映射）。
    金蝶数据已从海外仓迁移到国内仓，导入前会清理旧的海外仓金蝶仓库记录。
    """
    try:
        data = read_all_inventory()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Excel失败: {str(e)}")

    # 清空前备份备注：仓库+SKU 相同的行导入后自动保留
    remark_backup = crud_inventory.backup_remarks(db)

    # 清空旧库存
    deleted = crud_inventory.delete_all_inventory(db)

    # 清理旧的海外仓金蝶仓库记录（金蝶已迁移到国内仓）
    from app.models.inventory import Warehouse
    jindie_overseas_whs = db.query(Warehouse).filter(
        Warehouse.type == "overseas", Warehouse.platform == "金蝶"
    ).all()
    jindie_wh_count = len(jindie_overseas_whs)
    for wh in jindie_overseas_whs:
        db.delete(wh)
    if jindie_wh_count:
        db.flush()

    # 批量导入
    stats = crud_inventory.batch_import(db, data)

    # 责任人回填：导入清空重建后，按 sku_owner_map 自动补回（幂等覆盖式）
    owner_stats = apply_owner_backfill(db)

    # 备注恢复：仓库+SKU 相同的行回填（数据相同保留备注）
    remark_restored = crud_inventory.restore_remarks(db, remark_backup)

    return {
        "deleted_old": deleted,
        "deleted_jindie_warehouses": jindie_wh_count,
        "imported": stats["total"],
        "warehouses": stats["warehouses"],
        "goods": stats["goods"],
        "sku_mappings": stats["sku_mappings"],
        "owner_backfilled": owner_stats["updated"],
        "remark_restored": remark_restored,
        "message": f"成功导入 {stats['total']} 条库存（仓库 {stats['warehouses']} 个，商品 {stats['goods']} 个，清理旧金蝶海外仓 {jindie_wh_count} 个，责任人回填 {owner_stats['updated']} 行，备注保留 {remark_restored} 行）",
    }


@router.post("/import/domestic", summary="仅导入国内仓库存")
def import_domestic(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("data:import")),
):
    """仅导入国内仓数据（金蝶+澳霖），使用高性能批量导入"""
    from app.core.excel_reader import read_domestic_inventory
    try:
        items = read_domestic_inventory()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Excel失败: {str(e)}")

    data = {"domestic": items, "overseas": []}
    stats = crud_inventory.batch_import(db, data)
    return ImportResult(
        warehouse_type="国内仓", total_rows=len(items),
        imported_rows=stats["total"], skipped_rows=0,
        message=f"成功导入 {stats['total']} 条（仓库 {stats['warehouses']} 个，商品 {stats['goods']} 个）",
    )


@router.post("/owner-map/refresh", summary="刷新责任人映射并回填（读Excel）")
def owner_map_refresh(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("data:import")),
):
    """
    读取 责任人对应关系/亚马逊SKU明细.xlsx → upsert sku_owner_map（SKU与ASIN都入表）
    → 立即按映射回填 inventory.owner。
    Excel 更新后调用一次即可；一键导入后由 import-all 自动回填，无需手动调用。
    """
    try:
        map_stats = refresh_owner_map(db)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取责任人Excel失败: {str(e)}")

    apply_stats = apply_owner_backfill(db)
    return {
        "map_rows": map_stats["map_rows"],
        "backfilled": apply_stats["updated"],
        "by_path": apply_stats["by_path"],
        "message": (
            f"映射表已刷新 {map_stats['map_rows']} 条，回填库存 {apply_stats['updated']} 行"
            f"（{apply_stats['by_path']}）"
        ),
    }


# ========== 备注接口 ==========

@router.put("/remark", summary="更新库存备注")
def update_remark(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("data:import")),
):
    """
    更新单条库存备注：{inventory_id: int, remark: str}（清空传空串或 null）。
    备注手工维护，import-all 重新导入时按 仓库+SKU 相同自动保留。
    """
    inventory_id = data.get("inventory_id")
    if not isinstance(inventory_id, int):
        raise HTTPException(status_code=400, detail="inventory_id 必填且为整数")
    remark = data.get("remark")
    if remark is not None and not isinstance(remark, str):
        raise HTTPException(status_code=400, detail="remark 必须为字符串")
    if remark is not None and len(remark) > 500:
        raise HTTPException(status_code=400, detail="备注最长 500 字符")
    inv = crud_inventory.update_inventory_remark(db, inventory_id, remark)
    if not inv:
        raise HTTPException(status_code=404, detail="库存记录不存在")
    return {"inventory_id": inv.id, "remark": inv.remark}


# ========== 查询接口 ==========

@router.get("/list", summary="分页查询库存")
def list_inventory(
    pageNo: int = Query(1, ge=1, description="页码，从1开始"),
    pageSize: int = Query(20, ge=1, le=500, description="每页条数"),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或名称"),
    warehouse_id: Optional[int] = Query(None, description="按仓库ID筛选"),
    wh_type: Optional[str] = Query(None, description="按仓库类型筛选: domestic/overseas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页查询库存，返回 list + total + totalStock + warehouseCount + totalSkuNum（按角色平台权限过滤）"""
    allowed = crud_rbac.get_visible_platforms(db, current_user.id)
    items, total, stock_sum, wh_count, sku_num = crud_inventory.get_inventory_page(
        db, pageNo=pageNo, pageSize=pageSize, sku=sku,
        warehouse_id=warehouse_id, wh_type=wh_type,
        allowed_platforms=allowed,
    )
    return {
        "list": items,
        "total": total,
        "totalStock": stock_sum,
        "warehouseCount": wh_count,
        "totalSkuNum": sku_num,
        "pageNo": pageNo,
        "pageSize": pageSize,
    }


@router.get("/domestic", summary="分页查询国内仓库存")
def list_domestic(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=500),
    sku: Optional[str] = Query(None, description="模糊搜索SKU或名称"),
    platform: Optional[str] = Query(None, description="按平台筛选: 金蝶/澳霖"),
    country: Optional[str] = Query(None, description="按国家筛选"),
    warehouse_type: Optional[str] = Query(None, description="按数据来源文件名筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    分页查询国内仓库存，支持以下筛选方式（可组合）：
    - platform: 按平台筛选（金蝶/澳霖）
    - country: 按国家筛选
    - warehouse_type: 按数据来源文件名筛选
    - sku: 模糊搜索SKU或名称
    返回数据按当前用户角色平台权限强制过滤。
    """
    allowed = crud_rbac.get_visible_platforms(db, current_user.id)
    items, total, stock_sum, wh_count, sku_num = crud_inventory.get_inventory_page(
        db, pageNo=pageNo, pageSize=pageSize, sku=sku,
        wh_type="domestic", platform=platform, country=country,
        warehouse_type=warehouse_type, allowed_platforms=allowed,
    )
    return {"list": items, "total": total, "totalStock": stock_sum,
            "warehouseCount": wh_count, "totalSkuNum": sku_num,
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
    current_user: User = Depends(get_current_user),
):
    """
    分页查询海外仓库存，支持以下筛选方式（可组合）：
    - platform + country: 按平台和国家组合筛选
    - warehouse_type: 按数据来源文件名筛选（如 "中邮英国" 对应 海外仓/亚马逊/中邮英国.xlsx）
    - sku: 模糊搜索SKU或名称
    返回数据按当前用户角色平台权限强制过滤。
    """
    allowed = crud_rbac.get_visible_platforms(db, current_user.id)
    items, total, stock_sum, wh_count, sku_num = crud_inventory.get_inventory_page(
        db, pageNo=pageNo, pageSize=pageSize, sku=sku,
        wh_type="overseas", platform=platform, country=country,
        warehouse_type=warehouse_type, allowed_platforms=allowed,
    )
    return {"list": items, "total": total, "totalStock": stock_sum,
            "warehouseCount": wh_count, "totalSkuNum": sku_num,
            "pageNo": pageNo, "pageSize": pageSize}


# ========== 仓库列表 ==========

@router.get("/warehouses", summary="获取仓库列表")
def list_warehouses(
    wh_type: Optional[str] = Query(None, description="按类型筛选: domestic/overseas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取仓库列表（按当前用户平台权限过滤，仅返回可见平台的仓库）"""
    allowed = crud_rbac.get_visible_platforms(db, current_user.id)
    return crud_inventory.get_warehouses(db, wh_type=wh_type, allowed_platforms=allowed)


# ========== 商品列表 ==========

@router.get("/goods", summary="获取商品列表")
def list_goods(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取商品列表"""
    return crud_inventory.get_goods_list(db, skip=skip, limit=limit)


# ========== 汇总 ==========

@router.get("/summary", summary="库存汇总统计")
def inventory_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """库存汇总：总条数、总库存、仓库数、商品数、国内/海外分别多少（按角色平台权限过滤）"""
    allowed = crud_rbac.get_visible_platforms(db, current_user.id)
    return crud_inventory.get_inventory_summary(db, allowed_platforms=allowed)
