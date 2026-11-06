import time
import threading
import logging
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# 赛狐 API 配置（全局参数）
SELLFOX_CLIENT_ID = os.getenv("SELLFOX_CLIENT_ID", "")
SELLFOX_CLIENT_SECRET = os.getenv("SELLFOX_CLIENT_SECRET", "")
SELLFOX_GRANT_TYPE = "client_credentials"
SELLFOX_TOKEN_URL = "https://openapi.sellfox.com/api/oauth/v2/token.json"

# 提前刷新阈值（秒），留 5 分钟缓冲
_TOKEN_REFRESH_BUFFER = 300


class SellfoxTokenManager:
    """
    赛狐 access_token 管理器（线程安全单例）。

    职责：
    1. 获取 access_token 并缓存
    2. 有效期内重复获取返回相同 token
    3. 过期或失效时自动重新获取
    4. 避免频繁调用 token 接口（否则触发频率拦截）
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._token: str | None = None
        self._expires_at: float = 0  # Unix 时间戳（秒）
        self._token_lock = threading.Lock()

    def _is_valid(self) -> bool:
        """判断当前 token 是否仍然有效"""
        if not self._token:
            return False
        # 当前时间 + 缓冲 < 过期时间 → 仍有效
        return time.time() + _TOKEN_REFRESH_BUFFER < self._expires_at

    def _fetch_token(self) -> dict:
        """
        实际调用赛狐 API 获取 access_token。

        返回原始 JSON 数据：
        {
            "code": 0,
            "msg": "success",
            "data": {
                "access_token": "xxx",
                "expires_in": 86400000
            },
            "requestId": "xxx"
        }
        """
        params = {
            "client_id": SELLFOX_CLIENT_ID,
            "client_secret": SELLFOX_CLIENT_SECRET,
            "grant_type": SELLFOX_GRANT_TYPE,
        }

        logger.info("正在获取赛狐 access_token ...")

        with httpx.Client(timeout=30) as client:
            resp = client.get(SELLFOX_TOKEN_URL, params=params)
            resp.raise_for_status()
            result = resp.json()

        if result.get("code") != 0:
            raise RuntimeError(f"赛狐 token 获取失败: {result.get('msg', '未知错误')}")

        return result

    def get_token(self) -> str:
        """
        获取有效的 access_token。

        - 有效期内重复调用 → 返回缓存的 token
        - 过期或失效 → 自动重新获取
        - 线程安全，避免并发重复请求
        """
        # 快速路径：token 仍然有效
        if self._is_valid():
            return self._token

        # 慢路径：需要获取/刷新 token
        with self._token_lock:
            # double-check，防止并发时多个线程同时进入
            if self._is_valid():
                return self._token

            result = self._fetch_token()
            data = result["data"]

            self._token = data["access_token"]
            # expires_in 单位为毫秒，转换为秒
            expires_in_seconds = data["expires_in"] / 1000
            self._expires_at = time.time() + expires_in_seconds

            logger.info(
                "赛狐 access_token 获取成功，有效期: %.0f 小时",
                expires_in_seconds / 3600,
            )

            return self._token

    def invalidate(self):
        """手动使 token 失效，下次调用 get_token 会重新获取"""
        with self._token_lock:
            self._token = None
            self._expires_at = 0
            logger.info("赛狐 access_token 已手动失效，下次调用将重新获取")

    def get_token_info(self) -> dict:
        """
        获取当前 token 的状态信息（用于调试接口）。
        不触发刷新，只返回当前缓存状态。
        """
        remaining = max(0, int(self._expires_at - time.time())) if self._token else 0
        return {
            "has_token": self._token is not None,
            "is_valid": self._is_valid(),
            "expires_at": self._expires_at if self._token else None,
            "remaining_seconds": remaining,
            "client_id": SELLFOX_CLIENT_ID,
        }


# 全局单例
sellfox_token_manager = SellfoxTokenManager()
