"""
全局统一响应封装。

所有接口成功返回:
{
    "code": 200,
    "success": true,
    "data": <原始返回值>
}

所有接口失败返回:
{
    "code": 101,
    "success": false,
    "message": "错误信息"
}
"""
import json
import logging
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# 需要排除的路径（不包装这些路径的响应）
EXCLUDE_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


class UnifiedResponseMiddleware(BaseHTTPMiddleware):
    """
    全局响应统一封装中间件。

    拦截所有 JSON 响应，包装成统一格式:
    - 成功: {"code": 200, "success": true, "data": ...}
    - 失败: {"code": 101, "success": false, "message": ...}
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # 对文档/健康检查等路径直接放行
        if request.url.path in EXCLUDE_PATHS:
            return await call_next(request)

        response = await call_next(request)

        # 只处理 JSON 响应
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # 读取响应体
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 不是合法 JSON，原样返回
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # 已经是统一格式的不重复包装（比如异常处理器已处理）
        if isinstance(data, dict) and "code" in data and "success" in data:
            return Response(
                content=json.dumps(data, ensure_ascii=False, default=str),
                status_code=200,
                media_type="application/json",
            )

        # HTTP 状态码非 2xx 视为失败
        if response.status_code < 200 or response.status_code >= 300:
            # 提取 FastAPI 的错误 detail
            message = ""
            if isinstance(data, dict):
                detail = data.get("detail")
                if isinstance(detail, str):
                    message = detail
                elif isinstance(detail, list):
                    # Pydantic 校验错误
                    messages = []
                    for err in detail:
                        loc = " -> ".join(str(x) for x in err.get("loc", []))
                        msg = err.get("msg", "")
                        messages.append(f"{loc}: {msg}" if loc else msg)
                    message = "; ".join(messages)
                else:
                    message = str(detail)
            else:
                message = str(data)

            wrapped = {
                "code": 101,
                "success": False,
                "message": message or "请求失败",
            }
            return JSONResponse(content=wrapped, status_code=200)

        # 成功响应，包装成统一格式
        wrapped = {
            "code": 200,
            "success": True,
            "data": data,
        }
        return JSONResponse(content=wrapped, status_code=200)


def register_exception_handlers(app):
    """
    注册全局异常处理器。

    捕获未处理的异常，返回统一错误格式。
    """

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("未处理异常: %s", str(exc))
        return JSONResponse(
            status_code=200,
            content={
                "code": 101,
                "success": False,
                "message": str(exc) or "服务器内部错误",
            },
        )
