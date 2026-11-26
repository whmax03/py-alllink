"""
责任人（owner）回填模块（多平台）：
- refresh_owner_map: 读取 责任人对应关系 目录下的责任人 Excel，upsert 到 sku_owner_map：
  - 亚马逊SKU明细.xlsx（SKU 与 ASIN 都入表，owner 取负责人列）
  - 沃尔玛SKU明细.xlsx（MSKU 入表，owner 固定 姚艳华）
  - SHOPEE LAZADA TK  EBAY SKU明细.xlsx（按平台入表，Shopee/Lazada→金雨清+范家燕，
    eBay→黄海桂，TikTok→李柏霖+冯颖+彭嘉宇+吴双+储佳莉）
- apply_owner_backfill: 按映射表全部平台回填 inventory.owner：
  - 库存行先按本平台映射（inventory.sku ∈ 映射表），未命中再按任意平台映射
    匹配中文/英文品名（品名形态的 SKU 桥接）
- 导入流程（import-all 清空重建库存后）自动调用 apply_owner_backfill，保证责任人不丢；
  Excel 更新后调 POST /inventory/owner-map/refresh 刷新映射并立即回填。
"""
import os
import json
import logging

import openpyxl
from sqlalchemy.orm import Session

from app.core.excel_reader import ERP_DATA_SOURCE
from app.models.inventory import Inventory, Warehouse, SkuOwnerMap

logger = logging.getLogger(__name__)

OWNER_DIR = os.path.join(ERP_DATA_SOURCE, "责任人对应关系")
AMAZON_EXCEL_PATH = os.path.join(OWNER_DIR, "亚马逊SKU明细.xlsx")
WALMART_EXCEL_PATH = os.path.join(OWNER_DIR, "沃尔玛SKU明细.xlsx")
SHOPEE_EXCEL_PATH = os.path.join(OWNER_DIR, "SHOPEE LAZADA TK  EBAY SKU明细.xlsx")

# Shopee/Lazada/TK/EBAY 表的责任人规则（用户指定）
SHOPEE_RULE = {
    "Shopee": "金雨清+范家燕",
    "Lazada": "金雨清+范家燕",
    "eBay": "黄海桂",
    "TikTok": "李柏霖+冯颖+彭颖+彭嘉宇+吴双+储佳莉",
}
WALMART_OWNER = "姚艳华"
# Excel 平台名 → 映射表/库存平台名
SHOPEE_PLAT_MAP = {"Shopee": "Shopee", "Lazada": "Lazada", "eBay": "eBay", "TikTok": "Tiktok"}


def _upsert_map(db_engine, entries: list):
    """entries: [(platform, sku_key, owner)]，逐条 upsert 到 sku_owner_map"""
    from sqlalchemy import text
    with db_engine.begin() as conn:
        for plat, sku_key, owner_s in entries:
            conn.execute(text(
                "INSERT INTO sku_owner_map (platform, sku, owner) VALUES (:p, :s, :o) "
                "ON DUPLICATE KEY UPDATE owner = :o, updated_at = NOW()"
            ), {"p": plat, "s": sku_key, "o": owner_s})


def _read_amazon(db: Session) -> list:
    """亚马逊明细（SKU 与 ASIN 都入表，owner 取负责人列）"""
    if not os.path.exists(AMAZON_EXCEL_PATH):
        raise FileNotFoundError(f"责任人对应文件不存在: {AMAZON_EXCEL_PATH}")
    wb = openpyxl.load_workbook(AMAZON_EXCEL_PATH, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    entries = []
    seen = set()
    for r in rows[1:]:
        vals = (list(r) + [None] * 7)[:7]
        sku, asin, _status, _account, _site, _brand, owner = vals
        owner_s = str(owner).strip() if owner else ""
        for key in (str(sku).strip() if sku else "", str(asin).strip() if asin else ""):
            if not key or key == "Total" or not owner_s or key in seen:
                continue
            seen.add(key)
            entries.append(("亚马逊", key, owner_s))
    return entries


def _read_walmart(db: Session) -> list:
    """沃尔玛明细（MSKU 入表，owner 固定 姚艳华）"""
    if not os.path.exists(WALMART_EXCEL_PATH):
        raise FileNotFoundError(f"责任人对应文件不存在: {WALMART_EXCEL_PATH}")
    wb = openpyxl.load_workbook(WALMART_EXCEL_PATH, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    mskus = []
    seen = set()
    for r in rows[1:]:
        vals = (list(r) + [None] * 4)[:4]
        _time, msku, _shop, _site = vals
        key = str(msku).strip() if msku else ""
        if not key or key in seen:
            continue
        seen.add(key)
        mskus.append(("沃尔玛", key, WALMART_OWNER))
    return mskus


def _read_shopee_group(db: Session) -> list:
    """SHOPEE/LAZADA/TK/EBAY 明细（按平台入表，责任人按固定规则）"""
    if not os.path.exists(SHOPEE_EXCEL_PATH):
        raise FileNotFoundError(f"责任人对应文件不存在: {SHOPEE_EXCEL_PATH}")
    wb = openpyxl.load_workbook(SHOPEE_EXCEL_PATH, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    entries = []
    seen = set()
    for r in rows[1:]:
        vals = (list(r) + [None] * 3)[:3]
        plat, sku, _owner_col = vals
        if not plat or not sku:
            continue
        plat_s = str(plat).strip()
        key = str(sku).strip()
        owner = SHOPEE_RULE.get(plat_s)
        plat_db = SHOPEE_PLAT_MAP.get(plat_s)
        if not owner or not plat_db or not key or (plat_db, key) in seen:
            continue
        seen.add((plat_db, key))
        entries.append((plat_db, key, owner))
    return entries


def refresh_owner_map(db: Session) -> dict:
    """
    读取三份责任人 Excel → upsert sku_owner_map（多平台）。
    返回 {"map_rows": 总入表行数, "by_excel": 各文件行数}
    """
    from app.database import engine

    amazon = _read_amazon(db)
    walmart = _read_walmart(db)
    shopee_group = _read_shopee_group(db)
    entries = amazon + walmart + shopee_group

    _upsert_map(engine, entries)

    by_excel = {
        "亚马逊SKU明细.xlsx": len(amazon),
        "沃尔玛SKU明细.xlsx": len(walmart),
        "SHOPEE LAZADA TK  EBAY SKU明细.xlsx": len(shopee_group),
    }
    logger.info("责任人映射已刷新: %d 条入表 %s", len(entries), by_excel)
    return {"map_rows": len(entries), "by_excel": by_excel}


def _match_owner(db: Session) -> dict:
    """加载映射表全部平台（展平）→ {sku_key: owner}；供外部调试/旧兼容"""
    rows = db.query(SkuOwnerMap).all()
    return {r.sku: r.owner for r in rows}


def _row_names(raw_data: str, name_cn, name_en):
    """从 raw_data 提取字米类的首行中英文品名（非字米行回退到 name 字段）"""
    cn, en = name_cn or "", name_en or ""
    try:
        d = json.loads(raw_data) if isinstance(raw_data, str) else {}
        if isinstance(d, dict):
            rrows = d.get("rows", [])
            if rrows and isinstance(rrows[0], dict):
                first = rrows[0]
                cn = first.get("中文品名") or cn
                en = first.get("英文品名") or en
    except (ValueError, TypeError):
        pass
    return (cn or "").strip(), (en or "").strip()


def get_owner_matches(db: Session) -> list:
    """
    计算匹配（不写库）：
    匹配优先级（平台优先，避免跨平台同名 SKU 误归属）：
      1. inventory.sku ∈ 本平台映射（如 Shopee 库存行只先查 Shopee 映射）
      2. 中文/英文品名 ∈ 本平台映射（品名形态 SKU 桥接）
      3. 跨平台兜底：sku/品名 ∈ 任意平台映射（如字米仓品名==品牌 SKU）
    返回 [{id, sku, owner, path}, ...]，path ∈ {sku, name_cn, name_en}
    """
    all_rows = db.query(SkuOwnerMap).all()
    by_plat: dict = {}
    for r in all_rows:
        by_plat.setdefault(r.platform, {})[r.sku] = r.owner
    flat = {r.sku: r.owner for r in all_rows}
    if not flat:
        return []

    inv_rows = (
        db.query(Inventory.id, Inventory.sku, Inventory.name_cn,
                 Inventory.name_en, Inventory.raw_data, Warehouse.platform)
        .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
        .all()
    )

    matches = []
    for iid, sku, name_cn, name_en, raw_data, plat in inv_rows:
        sku = (sku or "").strip()
        plat_map = by_plat.get(plat, {})
        owner = None
        path = None
        if sku and sku in plat_map:
            owner, path = plat_map[sku], "sku"
        if owner is None:
            cn, en = _row_names(raw_data, name_cn, name_en)
            if cn and cn in plat_map:
                owner, path = plat_map[cn], "name_cn"
            elif en and en in plat_map:
                owner, path = plat_map[en], "name_en"
            elif sku and sku in flat:
                owner, path = flat[sku], "sku"
            elif cn and cn in flat:
                owner, path = flat[cn], "name_cn"
            elif en and en in flat:
                owner, path = flat[en], "name_en"
        if owner:
            matches.append({"id": iid, "sku": sku, "owner": owner, "path": path})
    return matches


def apply_owner_backfill(db: Session) -> dict:
    """
    按映射表回填 inventory.owner（幂等：覆盖式重算）。
    返回 {"updated": N, "by_path": {path: count}}
    """
    matches = get_owner_matches(db)
    by_path = {}
    for m in matches:
        by_path[m["path"]] = by_path.get(m["path"], 0) + 1

    if matches:
        ids = [m["id"] for m in matches]
        owner_by_id = {m["id"]: m["owner"] for m in matches}
        invs = db.query(Inventory).filter(Inventory.id.in_(ids)).all()
        for inv in invs:
            inv.owner = owner_by_id[inv.id]
        db.commit()

    logger.info("责任人回填完成: %d 行 %s", len(matches), by_path)
    return {"updated": len(matches), "by_path": by_path}
