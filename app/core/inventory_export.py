"""
库存导出：把查询结果写成 xlsx 字节流，并落一条导出审计日志。

设计要点：
- 复用 crud_inventory.get_inventory_page，筛选条件与平台权限白名单与页面查询完全一致，
  保证「页面上能看到什么，导出的就是什么」，前端传参只能缩小范围、不能扩大。
- 分块取数（每块 chunk_size 行）再流式写 sheet，避免全量导出时一次性把几万行读进内存。
- 列定义按仓类型区分：国内仓多「计划跟踪号」，海外仓多「责任人」。
"""
import json
import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.crud import inventory as crud_inventory
from app.models.export_log import InventoryExportLog
from app.models.user import User

logger = logging.getLogger(__name__)

# 单次导出行数上限：防止误点全量导出把服务内存/带宽打满
MAX_EXPORT_ROWS = 100000
CHUNK_SIZE = 2000
# Excel 单列字符上限 32767，超长文本截断避免写出损坏文件
MAX_CELL_CHARS = 32000


def _text(value) -> str:
    """任意值转为单元格文本：None → 空串，超长截断。"""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False)
    else:
        s = str(value)
    return s[:MAX_CELL_CHARS]


def _row_to_values(item: dict, columns: List[Tuple[str, str]], wh_label: str) -> List[str]:
    """把一条库存记录按列定义拍平成单元格值列表。"""
    raw = item.get("raw_data") or {}
    warehouse = item.get("warehouse") or {}
    values: List[str] = []
    for key, _label in columns:
        if key == "warehouse_code":
            values.append(_text(warehouse.get("code")))
        elif key == "platform":
            values.append(_text(warehouse.get("platform")))
        elif key == "warehouse_name":
            values.append(_text(wh_label))
        elif key == "sku":
            # 与页面展示一致：优先 original_sku（原始 SKU 字段），回退 sku
            values.append(_text(raw.get("original_sku") or item.get("sku")))
        elif key == "product_name":
            values.append(_text(raw.get("产品标题") or item.get("name_cn") or item.get("name_en")))
        elif key == "barcode":
            values.append(_text(raw.get("产品条码") or raw.get("条码")))
        elif key == "tracking_no":
            values.append(_text(raw.get("计划跟踪号")))
        elif key == "unit":
            values.append(_text(item.get("stock_unit") or raw.get("产品单位") or raw.get("库存主单位")))
        elif key == "imported_at":
            ts = item.get("imported_at")
            if isinstance(ts, datetime):
                values.append(ts.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                values.append(_text(ts))
        else:
            values.append(_text(item.get(key)))
    return values


def export_inventory_xlsx(
    db: Session,
    *,
    scope: str,
    columns: List[Tuple[str, str]],
    sheet_title: str,
    allowed_platforms: Optional[List[str]],
    sku: Optional[str] = None,
    platform: Optional[str] = None,
    country: Optional[str] = None,
    warehouse_type: Optional[str] = None,
    mode: str = "filtered",
    filters_desc: Optional[Dict] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Tuple[BytesIO, int]:
    """
    生成库存导出文件。

    scope: domestic / overseas（同时作为 get_inventory_page 的 wh_type）
    mode:  all=全量（忽略筛选）/ filtered=按页面当前筛选
    sort_by / sort_order: 与页面当前排序一致，保证导出的行序和屏幕上看到的一致
    返回 (文件字节流, 导出行数)
    """
    use_filters = mode != "all"
    sku_f = sku if use_filters else None
    platform_f = platform if use_filters else None
    country_f = country if use_filters else None
    wt_f = warehouse_type if use_filters else None

    # 先按当前条件取总数，判断是否超上限（count 很轻，不需要把所有行读出来）
    _, total, _, _, _ = crud_inventory.get_inventory_page(
        db, pageNo=1, pageSize=1, sku=sku_f,
        wh_type=scope, platform=platform_f, country=country_f,
        warehouse_type=wt_f, allowed_platforms=allowed_platforms,
    )
    if total > MAX_EXPORT_ROWS:
        raise ValueError(f"本次导出 {total} 行，超过单次上限 {MAX_EXPORT_ROWS} 行，请先缩小筛选范围")

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title

    # ---- 表头样式 ----
    header_fill = PatternFill("solid", fgColor="EFF6FF")
    header_font = Font(bold=True, color="1E293B", size=11)
    headers = [label for _key, label in columns]
    headers = ["NO."] + headers
    ws.append(headers)
    for idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(idx)].width = 8 if idx == 1 else 18

    # 冻结表头 + 自动筛选（和页面表格的操作手感一致）
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    # ---- 分块取数写入 ----
    written = 0
    page_no = 1
    while written < total:
        items, _, _, _, _ = crud_inventory.get_inventory_page(
            db, pageNo=page_no, pageSize=CHUNK_SIZE, sku=sku_f,
            wh_type=scope, platform=platform_f, country=country_f,
            warehouse_type=wt_f, allowed_platforms=allowed_platforms,
            sort_by=sort_by, sort_order=sort_order,
        )
        if not items:
            break
        for item in items:
            wh_label = (item.get("warehouse") or {}).get("warehouse_type") or ""
            ws.append([written + 1] + _row_to_values(item, columns, wh_label))
            written += 1
        page_no += 1

    # 数值列（可用库存）右对齐
    for row in ws.iter_rows(min_row=2, max_row=written + 1):
        for cell in row:
            cell.alignment = Alignment(vertical="center")

    buf = BytesIO()
    wb.save(buf)
    wb.close()
    buf.seek(0)
    return buf, written


def write_export_log(
    db: Session,
    *,
    user: User,
    scope: str,
    mode: str,
    filters_desc: Optional[Dict],
    row_count: int,
) -> None:
    """写导出审计日志。失败只记录错误，不影响导出主流程（文件已经生成好了）。"""
    try:
        db.add(InventoryExportLog(
            user_id=getattr(user, "id", None),
            user_name=getattr(user, "name", None),
            user_email=getattr(user, "email", None),
            scope=scope,
            mode=mode,
            filters=json.dumps(filters_desc, ensure_ascii=False) if filters_desc else None,
            row_count=row_count,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 - 审计日志失败不能影响用户拿到导出文件
        logger.exception("写库存导出审计日志失败")
        db.rollback()
