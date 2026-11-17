"""
Excel 读取服务 — 读取 ERP 数据源目录下的所有库存 Excel 文件，适配新表结构。

数据源路径: C:\\Users\\Administrator\\Desktop\\ERP数据源
  ├── 国内仓/skuList.xlsx          (国内仓 ERP 数据)
  └── 海外仓/
      ├── Shopee/  (印尼.xls/泰国.xlsx/菲律宾.xlsx/马来.xlsx)
      ├── Tiktok/  (泰国库存.xlsx/马来库存.xlsx)
      ├── eBay/    (AU仓库.xlsx/UK仓库.xlsx)
      ├── 亚马逊/  (VC海外仓德国站/中邮德国/中邮英国/字米前置转运仓美国/字米美国/派速捷德国)
      └── 金蝶/    (skuList.xlsx)

每个文件读取后返回统一的 inventory 行格式:
  {warehouse_id, sku, name_cn, name_en, spec, stock_qty, available_qty,
   frozen_qty, outbound_qty, inbound_qty, raw_data}
"""
import os
import logging
import openpyxl
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 数据源根目录
ERP_DATA_SOURCE = r"C:\Users\Administrator\Desktop\ERP数据源"


# ========== 工具函数 ==========

def _safe_get(row, idx):
    """安全取值"""
    if idx < len(row) and row[idx] is not None:
        val = row[idx]
        if isinstance(val, str):
            return val.strip()
        return val
    return None


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_str(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _read_excel(file_path: str) -> List[tuple]:
    """读取 Excel 文件所有行（支持 .xlsx），返回 (header, data_rows) 的列表"""
    if file_path.endswith(".xls"):
        # .xls 格式需要 xlrd
        import xlrd
        wb = xlrd.open_workbook(file_path)
        sheet = wb.sheet_by_index(0)
        rows = []
        for r in range(sheet.nrows):
            rows.append(tuple(sheet.cell_value(r, c) for c in range(sheet.ncols)))
        return rows
    else:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        return rows


def _parse_rows(rows: list, expected_header_len: int = None) -> List[dict]:
    """将行数据解析为 list[dict]，第一行为表头"""
    if not rows:
        return []
    header = rows[0]
    result = []
    for row in rows[1:]:
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        d = {}
        for idx, h in enumerate(header):
            if h is None:
                continue
            key = str(h).strip()
            d[key] = _safe_get(row, idx)
        result.append(d)
    return result


def _group_by_sku_merged(parsed: List[dict], key_field: str = "sku") -> List[dict]:
    """
    合并「纵向展开」型表格：同一 SKU 因多个入库批次占多行时，
    续行仅包含批次信息（入库ID/入库时间），业务字段为空。

    返回: 每条记录一个 SKU，附带
      _inbound_ids    — 入库ID 字符串列表
      _inbound_times  — 入库时间字符串列表
      _raw_rows       — 原始所有行的字段列表（供 raw_data 完整保留）
    """
    groups: List[dict] = []
    for d in parsed:
        sku = _to_str(d.get(key_field))
        if sku:
            # 新 SKU 起始行
            g = dict(d)
            g["_inbound_ids"] = []
            g["_inbound_times"] = []
            g["_raw_rows"] = [dict(d)]
            inbound_id = _to_str(d.get("入库ID"))
            if inbound_id:
                g["_inbound_ids"].append(inbound_id)
                g["_inbound_times"].append(_to_str(d.get("入库时间")) or "")
            groups.append(g)
        elif groups:
            # 续行：把批次信息追加到上一个 SKU
            g = groups[-1]
            g["_raw_rows"].append(dict(d))
            inbound_id = _to_str(d.get("入库ID"))
            if inbound_id:
                g["_inbound_ids"].append(inbound_id)
                g["_inbound_times"].append(_to_str(d.get("入库时间")) or "")
                # 续行若带有库存数，取第一个非空值补充（部分表续行才有库存）
                for f in ("库存", "库存总数"):
                    if not g.get(f) and d.get(f) is not None:
                        g[f] = d.get(f)
                        break
    return groups


# ========== 国内仓 ==========

def read_domestic_inventory() -> List[Dict[str, Any]]:
    """
    读取国内仓 skuList.xlsx。
    表头: 物料编码 | 物料名称 | 规格型号 | 计划跟踪号 | 仓库名称 | 库存主单位 | 库存量(主单位)

    返回 inventory 行格式，warehouse_info 里有仓库信息供导入时建 warehouse。
    """
    file_path = os.path.join(ERP_DATA_SOURCE, "国内仓", "skuList.xlsx")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"国内仓文件不存在: {file_path}")

    logger.info("读取国内仓: %s", file_path)
    rows = _read_excel(file_path)
    parsed = _parse_rows(rows)

    result = []
    for d in parsed:
        material_code = _to_str(d.get("物料编码"))
        # 跳过 Excel 合计行
        if material_code and "合计" in material_code:
            continue
        warehouse_name = _to_str(d.get("仓库名称")) or "国内仓"
        result.append({
            "warehouse": {
                "name": warehouse_name,
                "code": warehouse_name,
                "type": "domestic",
                "platform": "ERP",
                "country": "中国",
                "warehouse_type": "skuList",
            },
            "sku": _to_str(d.get("物料编码")),
            "name_cn": _to_str(d.get("物料名称")),
            "name_en": None,
            "spec": _to_str(d.get("规格型号")),
            "stock_qty": _to_float(d.get("库存量(主单位)")) or 0,
            "available_qty": _to_float(d.get("库存量(主单位)")) or 0,
            "frozen_qty": 0,
            "outbound_qty": 0,
            "inbound_qty": 0,
            "raw_data": {
                "material_code": _to_str(d.get("物料编码")),
                "material_name": _to_str(d.get("物料名称")),
                "spec_model": _to_str(d.get("规格型号")),
                "plan_tracking_no": _to_str(d.get("计划跟踪号")),
                "warehouse_name": warehouse_name,
                "stock_unit": _to_str(d.get("库存主单位")),
                "stock_qty": _to_float(d.get("库存量(主单位)")),
            },
        })

    logger.info("国内仓读取完成: %d 条", len(result))
    return result


# ========== 海外仓 — eBay ==========

def read_ebay_inventory() -> List[Dict[str, Any]]:
    """读取 eBay AU/UK 仓库文件"""
    base = os.path.join(ERP_DATA_SOURCE, "海外仓", "eBay")
    result = []

    for fname in os.listdir(base) if os.path.isdir(base) else []:
        if not fname.endswith(".xlsx"):
            continue
        file_path = os.path.join(base, fname)
        # 跳过 Excel 临时文件
        if fname.startswith("~$"):
            continue
        wh_type = os.path.splitext(fname)[0]  # 文件名（不含扩展名）
        logger.info("读取 eBay: %s", fname)
        rows = _read_excel(file_path)
        parsed = _parse_rows(rows)

        for d in parsed:
            country = _to_str(d.get("国家")) or ""
            wh_code = _to_str(d.get("仓库")) or ""
            result.append({
                "warehouse": {
                    "name": f"eBay-{country}-{wh_code}",
                    "code": wh_code,
                    "type": "overseas",
                    "platform": "eBay",
                    "country": country,
                    "warehouse_type": wh_type,
                },
                "sku": _to_str(d.get("商品编号")),
                "name_cn": _to_str(d.get("中文名称")),
                "name_en": _to_str(d.get("英文名称")),
                "spec": _to_str(d.get("规格")),
                "stock_qty": _to_float(d.get("在库库存")) or 0,
                "available_qty": _to_float(d.get("可用库存")) or 0,
                "frozen_qty": _to_float(d.get("返架中")) or 0,
                "outbound_qty": _to_float(d.get("待出库")) or 0,
                "inbound_qty": 0,
                "raw_data": {k: _to_str(v) for k, v in d.items()},
            })

    logger.info("eBay 读取完成: %d 条", len(result))
    return result


# ========== 海外仓 — Shopee ==========

def read_shopee_inventory() -> List[Dict[str, Any]]:
    """读取 Shopee 各国家文件（兼容两种表头格式）"""
    base = os.path.join(ERP_DATA_SOURCE, "海外仓", "Shopee")
    result = []

    country_map = {"印尼": "印度尼西亚", "泰国": "泰国", "菲律宾": "菲律宾", "马来": "马来西亚"}

    for fname in os.listdir(base) if os.path.isdir(base) else []:
        if not fname.endswith((".xlsx", ".xls")):
            continue
        file_path = os.path.join(base, fname)
        if fname.startswith("~$"):
            continue
        wh_type = os.path.splitext(fname)[0]
        country = country_map.get(wh_type, wh_type)
        logger.info("读取 Shopee: %s", fname)

        rows = _read_excel(file_path)
        parsed = _parse_rows(rows)
        if not parsed:
            continue

        first = parsed[0]

        if "库存SKU" in first:
            # 印尼.xls 格式：产品中文名 | 产品英文名 | 库存量 | 仓库 | 库存SKU | 在途量 | 待发货量 | 入库时间 | 可用库存
            for d in parsed:
                wh_code = _to_str(d.get("仓库")) or ""
                result.append({
                    "warehouse": {
                        "name": f"Shopee-{country}-{wh_code}",
                        "code": wh_code,
                        "type": "overseas",
                        "platform": "Shopee",
                        "country": country,
                        "warehouse_type": wh_type,
                    },
                    "sku": _to_str(d.get("库存SKU")),
                    "name_cn": _to_str(d.get("产品中文名")),
                    "name_en": _to_str(d.get("产品英文名")),
                    "spec": None,
                    "barcode": None,
                    "stock_qty": _to_float(d.get("库存量")) or 0,
                    "available_qty": _to_float(d.get("可用库存")) or 0,
                    "frozen_qty": 0,
                    "outbound_qty": _to_float(d.get("待发货量")) or 0,
                    "inbound_qty": _to_float(d.get("在途量")) or 0,
                    "raw_data": {k: _to_str(v) for k, v in d.items()},
                })
        else:
            # 泰国/菲律宾/马来 格式：含 商家内部SKU/主商品名称/仓库名称/编码/总库存/可用库存 等
            for d in parsed:
                wh_code = _to_str(d.get("仓库名称/编码")) or ""
                result.append({
                    "warehouse": {
                        "name": f"Shopee-{country}-{wh_code}",
                        "code": wh_code,
                        "type": "overseas",
                        "platform": "Shopee",
                        "country": country,
                        "warehouse_type": wh_type,
                    },
                    "sku": _to_str(d.get("商家内部SKU")),
                    "name_cn": _to_str(d.get("主商品名称")),
                    "name_en": None,
                    "spec": _to_str(d.get("主商品规格")),
                    "barcode": _to_str(d.get("Barcode")),
                    "stock_qty": _to_float(d.get("总库存/总在库库存")) or 0,
                    "available_qty": _to_float(d.get("总库存/可用库存")) or 0,
                    "frozen_qty": _to_float(d.get("总库存/已占用库存")) or 0,
                    "outbound_qty": _to_float(d.get("总库存/已占用库存")) or 0,
                    "inbound_qty": _to_float(d.get("总库存/在途库存")) or 0,
                    "raw_data": {k: _to_str(v) for k, v in d.items()},
                })

    logger.info("Shopee 读取完成: %d 条", len(result))
    return result


# ========== 海外仓 — Tiktok ==========

def read_tiktok_inventory() -> List[Dict[str, Any]]:
    """读取 Tiktok 泰国/马来库存文件"""
    base = os.path.join(ERP_DATA_SOURCE, "海外仓", "Tiktok")
    result = []

    country_map = {"泰国库存": "泰国", "马来库存": "马来西亚"}

    for fname in os.listdir(base) if os.path.isdir(base) else []:
        if not fname.endswith(".xlsx"):
            continue
        file_path = os.path.join(base, fname)
        if fname.startswith("~$"):
            continue
        wh_type = os.path.splitext(fname)[0]
        country_key = wh_type
        country = country_map.get(country_key, country_key)
        logger.info("读取 Tiktok: %s", fname)

        rows = _read_excel(file_path)
        parsed = _parse_rows(rows)

        for d in parsed:
            wh_code = _to_str(d.get("仓库名称/编码")) or ""
            result.append({
                "warehouse": {
                    "name": f"Tiktok-{country}-{wh_code}",
                    "code": wh_code,
                    "type": "overseas",
                    "platform": "Tiktok",
                    "country": country,
                    "warehouse_type": wh_type,
                },
                "sku": _to_str(d.get("商家内部SKU")),
                "name_cn": _to_str(d.get("主商品名称")),
                "name_en": None,
                "spec": _to_str(d.get("主商品规格")),
                "barcode": _to_str(d.get("Barcode")),
                "stock_qty": _to_float(d.get("可用库存")) or 0,
                "available_qty": _to_float(d.get("可用库存")) or 0,
                "frozen_qty": 0,
                "outbound_qty": _to_float(d.get("待出库")) or 0,
                "inbound_qty": 0,
                "raw_data": {k: _to_str(v) for k, v in d.items()},
            })

    logger.info("Tiktok 读取完成: %d 条", len(result))
    return result


# ========== 海外仓 — 亚马逊 ==========

def read_amazon_inventory() -> List[Dict[str, Any]]:
    """读取亚马逊各仓库文件"""
    base = os.path.join(ERP_DATA_SOURCE, "海外仓", "亚马逊")
    result = []

    for fname in os.listdir(base) if os.path.isdir(base) else []:
        if not fname.endswith(".xlsx"):
            continue
        file_path = os.path.join(base, fname)
        if fname.startswith("~$"):
            continue
        wh_type = os.path.splitext(fname)[0]
        logger.info("读取亚马逊: %s", fname)
        rows = _read_excel(file_path)

        # 不同文件表头不同，需要兼容处理
        parsed = _parse_rows(rows)
        if not parsed:
            continue

        first = parsed[0]
        platform = "亚马逊"

        # 判断文件类型（顺序重要：具体格式优先，避免被通用条件抢先命中）
        if "客户" in first and "国家(仓库)" in first:
            # 字米美国 — Sheet: 一件代发库存
            # 该表为纵向展开结构：同一 SKU 因多个「入库ID/入库时间」占多行，
            # 前面的业务字段只在首行有值，续行仅填入库批次信息。
            # 这里按 SKU 分组合并，一个 SKU 一条库存记录，入库ID 汇总成 list。
            grouped = _group_by_sku_merged(parsed)
            for g in grouped:
                country_wh = g.get("国家(仓库)") or ""
                inbound_ids = g.get("_inbound_ids", [])
                inbound_times = g.get("_inbound_times", [])
                result.append({
                    "warehouse": {
                        "name": f"亚马逊-{country_wh}",
                        "code": country_wh,
                        "type": "overseas",
                        "platform": platform,
                        "country": None,
                        "warehouse_type": wh_type,
                    },
                    "sku": _to_str(g.get("sku")),
                    "name_cn": _to_str(g.get("中文品名")),
                    "name_en": _to_str(g.get("英文品名")),
                    "spec": None,
                    "stock_qty": _to_float(g.get("库存总数")) or 0,
                    "available_qty": _to_float(g.get("库存")) or 0,
                    "frozen_qty": 0,
                    "outbound_qty": _to_float(g.get("出库(已出库/出库数/冻结数)")) or 0,
                    "inbound_qty": 0,
                    "inbound_ids": inbound_ids,
                    "raw_data": {
                        "rows": [
                            {k: _to_str(v) for k, v in row.items() if not k.startswith("_")}
                            for row in g.get("_raw_rows", [])
                        ],
                        "入库ID列表": inbound_ids,
                        "入库时间列表": inbound_times,
                        "入库批次数": len(inbound_ids),
                    },
                })

        elif "客户" in first and "箱唛号" in first:
            # 字米前置转运仓美国 — Sheet: 库存信息
            for d in parsed:
                country = _to_str(d.get("国家")) or ""
                wh_name = _to_str(d.get("仓库")) or ""
                result.append({
                    "warehouse": {
                        "name": f"亚马逊-{country}-{wh_name}",
                        "code": wh_name,
                        "type": "overseas",
                        "platform": platform,
                        "country": country,
                        "warehouse_type": wh_type,
                    },
                    "sku": _to_str(d.get("sku")),
                    "name_cn": None,
                    "name_en": None,
                    "spec": _to_str(d.get("箱唛号")),
                    "stock_qty": _to_float(d.get("库存数量")) or 0,
                    "available_qty": _to_float(d.get("库存")) or 0,
                    "frozen_qty": _to_float(d.get("冻结")) or 0,
                    "outbound_qty": 0,
                    "inbound_qty": 0,
                    "raw_data": {k: _to_str(v) for k, v in d.items()},
                })

        elif "产品条码" in first or "sku" in first or "SKU" in first:
            # 亚马逊标准格式（VC海外仓德国站/派速捷德国/中邮德国/中邮英国）
            for d in parsed:
                wh_code = _to_str(d.get("仓库")) or ""
                sku_val = _to_str(d.get("sku") or d.get("SKU"))
                barcode = _to_str(d.get("产品条码"))
                result.append({
                    "warehouse": {
                        "name": f"亚马逊-{wh_type}-{wh_code}",
                        "code": wh_code,
                        "type": "overseas",
                        "platform": platform,
                        "country": None,
                        "warehouse_type": wh_type,
                    },
                    "sku": sku_val,
                    "name_cn": _to_str(d.get("产品标题") or d.get("产品名称")),
                    "name_en": _to_str(d.get("产品标题EN")),
                    "spec": None,
                    "barcode": barcode,
                    "product_code": _to_str(d.get("自定义编码")),
                    "stock_qty": _to_float(d.get("可售")) or 0,
                    "available_qty": _to_float(d.get("可售")) or 0,
                    "frozen_qty": _to_float(d.get("冻结")) or 0,
                    "outbound_qty": _to_float(d.get("待出库")) or 0,
                    "inbound_qty": _to_float(d.get("在途")) or 0,
                    "raw_data": {k: _to_str(v) for k, v in d.items()},
                })

    logger.info("亚马逊读取完成: %d 条", len(result))
    return result


# ========== 海外仓 — 金蝶 ==========

def read_jindie_inventory() -> List[Dict[str, Any]]:
    """
    读取金蝶 skuList.xlsx（海外仓/金蝶/ 目录下）。
    表头: 物料编码 | 物料名称 | 规格型号 | 计划跟踪号 | 仓库名称 | 批号 | 库存主单位 |
          库存量(主单位) | 可用量(主单位) | 库存状态 | ... | 条码 | CDC

    每个文件作为一个 warehouse_type，文件名去掉扩展名即为 warehouse_type。
    返回 inventory 行格式，warehouse_info 里有仓库信息供导入时建 warehouse。
    """
    base = os.path.join(ERP_DATA_SOURCE, "海外仓", "金蝶")
    result = []

    for fname in os.listdir(base) if os.path.isdir(base) else []:
        if not fname.endswith((".xlsx", ".xls")):
            continue
        if fname.startswith("~$"):
            continue
        file_path = os.path.join(base, fname)
        wh_type = os.path.splitext(fname)[0]
        logger.info("读取金蝶: %s", fname)

        rows = _read_excel(file_path)
        parsed = _parse_rows(rows)

        for d in parsed:
            material_code = _to_str(d.get("物料编码"))
            # 跳过合计行
            if material_code and "合计" in material_code:
                continue
            # 跳过空行
            if not material_code and not d.get("物料名称"):
                continue

            warehouse_name = _to_str(d.get("仓库名称")) or "金蝶仓"
            barcode = _to_str(d.get("条码"))
            result.append({
                "warehouse": {
                    "name": f"金蝶-{warehouse_name}",
                    "code": warehouse_name,
                    "type": "overseas",
                    "platform": "金蝶",
                    "country": "中国",
                    "warehouse_type": wh_type,
                },
                "sku": material_code,
                "name_cn": _to_str(d.get("物料名称")),
                "name_en": None,
                "spec": _to_str(d.get("规格型号")),
                "barcode": barcode,
                "product_code": None,
                "stock_qty": _to_float(d.get("库存量(主单位)")) or 0,
                "available_qty": _to_float(d.get("可用量(主单位)")) or 0,
                "frozen_qty": 0,
                "outbound_qty": 0,
                "inbound_qty": 0,
                "raw_data": {k: _to_str(v) for k, v in d.items()},
            })

    logger.info("金蝶读取完成: %d 条", len(result))
    return result


# ========== 一键读取全部 ==========

def read_all_inventory() -> Dict[str, List[Dict[str, Any]]]:
    """
    读取所有数据源，按仓库类型分组返回。
    返回: {"domestic": [...], "overseas": [...]}
    """
    domestic = []
    overseas = []

    # 国内仓
    try:
        domestic = read_domestic_inventory()
    except Exception as e:
        logger.error("读取国内仓失败: %s", e)

    # 海外仓 — 各平台
    for reader_fn in [read_ebay_inventory, read_shopee_inventory,
                      read_tiktok_inventory, read_amazon_inventory,
                      read_jindie_inventory]:
        try:
            overseas.extend(reader_fn())
        except Exception as e:
            logger.error("读取海外仓失败 (%s): %s", reader_fn.__name__, e)

    logger.info("全部读取完成: 国内仓 %d 条, 海外仓 %d 条", len(domestic), len(overseas))
    return {"domestic": domestic, "overseas": overseas}
