"""
Excel 读取服务 — 读取 ERP 数据源目录下的国内仓和海外仓库存 Excel 文件。

数据源路径: C:\\Users\\Administrator\\Desktop\\ERP数据源
  ├── 国内仓/即时库存澳霖汇总.xlsx
  └── 海外仓/skuList.xlsx
"""
import os
import logging
import openpyxl
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# 数据源根目录
ERP_DATA_SOURCE = r"C:\Users\Administrator\Desktop\ERP数据源"

# 文件路径
DOMESTIC_FILE = os.path.join(ERP_DATA_SOURCE, "国内仓", "skuList.xlsx")
OVERSEAS_FILE = os.path.join(ERP_DATA_SOURCE, "海外仓", "skuList.xlsx")


def read_domestic_inventory(file_path: str = DOMESTIC_FILE) -> List[Dict[str, Any]]:
    """
    读取国内仓库存 Excel 文件。

    列结构: 物料编码 | 物料名称 | 规格型号 | 计划跟踪号 | 仓库名称 | 库存主单位 | 库存量(主单位)

    返回: [{material_code, material_name, spec_model, plan_tracking_no,
           warehouse_name, stock_unit, stock_qty}, ...]
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"国内仓文件不存在: {file_path}")

    logger.info("正在读取国内仓文件: %s", file_path)
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]

    rows_data = []
    header = None

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = row
            continue

        # 跳过空行
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        # 安全取值（按列索引）
        def safe_get(idx):
            if idx < len(row) and row[idx] is not None:
                val = row[idx]
                if isinstance(val, str):
                    return val.strip()
                return val
            return None

        stock_qty = safe_get(6)
        # 尝试转为 float
        if stock_qty is not None:
            try:
                stock_qty = float(stock_qty)
            except (ValueError, TypeError):
                stock_qty = None

        rows_data.append({
            "material_code": safe_get(0),
            "material_name": safe_get(1),
            "spec_model": safe_get(2),
            "plan_tracking_no": safe_get(3),
            "warehouse_name": safe_get(4),
            "stock_unit": safe_get(5),
            "stock_qty": stock_qty,
        })

    wb.close()
    logger.info("国内仓读取完成，共 %d 条数据", len(rows_data))
    return rows_data


def read_overseas_inventory(file_path: str = OVERSEAS_FILE) -> List[Dict[str, Any]]:
    """
    读取海外仓库存 Excel 文件。

    列结构: 客户 | sku | 国家(仓库) | 中文品名 | 英文品名 | 库存总数 |
            出库(已出库/出库数/冻结数) | 入库ID | 库存 | 入库时间 | 存放天数

    注意: 海外仓文件存在合并单元格导致的空行，需要用上一行有效数据填充。

    返回: [{customer, sku, country_warehouse, cn_name, en_name,
           total_stock, outbound_info, inbound_id, stock,
           inbound_date, storage_days}, ...]
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"海外仓文件不存在: {file_path}")

    logger.info("正在读取海外仓文件: %s", file_path)
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]

    rows_data = []
    header = None

    # 用于填充合并单元格空行的上一行有效值
    last_valid = {
        "customer": None,
        "sku": None,
        "country_warehouse": None,
        "cn_name": None,
        "en_name": None,
        "total_stock": None,
        "outbound_info": None,
    }

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = row
            continue

        # 跳过完全空行
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        def safe_get(idx):
            if idx < len(row) and row[idx] is not None:
                val = row[idx]
                if isinstance(val, str):
                    return val.strip()
                return val
            return None

        # 如果前几列为空（合并单元格情况），用上一行有效值填充
        customer = safe_get(0)
        sku = safe_get(1)
        country_warehouse = safe_get(2)
        cn_name = safe_get(3)
        en_name = safe_get(4)
        total_stock = safe_get(5)
        outbound_info = safe_get(6)

        if customer is None:
            customer = last_valid["customer"]
        else:
            last_valid["customer"] = customer

        if sku is None:
            sku = last_valid["sku"]
        else:
            last_valid["sku"] = sku

        if country_warehouse is None:
            country_warehouse = last_valid["country_warehouse"]
        else:
            last_valid["country_warehouse"] = country_warehouse

        if cn_name is None:
            cn_name = last_valid["cn_name"]
        else:
            last_valid["cn_name"] = cn_name

        if en_name is None:
            en_name = last_valid["en_name"]
        else:
            last_valid["en_name"] = en_name

        if total_stock is None:
            total_stock = last_valid["total_stock"]
        else:
            last_valid["total_stock"] = total_stock

        if outbound_info is None:
            outbound_info = last_valid["outbound_info"]
        else:
            last_valid["outbound_info"] = outbound_info

        # 转换 total_stock
        if total_stock is not None:
            try:
                total_stock = float(total_stock)
            except (ValueError, TypeError):
                total_stock = None

        # 转换 storage_days
        storage_days = safe_get(10)
        if storage_days is not None:
            try:
                storage_days = int(float(storage_days))
            except (ValueError, TypeError):
                storage_days = None

        rows_data.append({
            "customer": customer,
            "sku": sku,
            "country_warehouse": country_warehouse,
            "cn_name": cn_name,
            "en_name": en_name,
            "total_stock": total_stock,
            "outbound_info": outbound_info,
            "inbound_id": safe_get(7),
            "stock": safe_get(8) if safe_get(8) is not None else str(safe_get(8) or ""),
            "inbound_date": str(safe_get(9)) if safe_get(9) is not None else None,
            "storage_days": storage_days,
        })

    wb.close()
    logger.info("海外仓读取完成，共 %d 条数据", len(rows_data))
    return rows_data
