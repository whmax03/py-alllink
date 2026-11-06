from fastapi import APIRouter, HTTPException

from app.core.sellfox_client import sellfox_token_manager

router = APIRouter(prefix="/sellfox", tags=["赛狐API"])


@router.get("/token", summary="查看token状态")
def get_sellfox_token_info():
    """查看当前赛狐 access_token 的缓存状态（不暴露 token 本身）"""
    return sellfox_token_manager.get_token_info()


@router.post("/token/refresh", summary="刷新token")
def refresh_sellfox_token():
    """手动使 access_token 失效并重新获取"""
    sellfox_token_manager.invalidate()
    try:
        new_token = sellfox_token_manager.get_token()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"token 获取失败: {str(e)}")

    return {
        "access_token": new_token,
        **sellfox_token_manager.get_token_info(),
    }


@router.get("/token/raw", summary="获取token字符串")
def get_sellfox_token_raw():
    """获取实际的 access_token 字符串（仅供调试）"""
    try:
        token = sellfox_token_manager.get_token()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"token 获取失败: {str(e)}")

    return {
        "access_token": token,
        **sellfox_token_manager.get_token_info(),
    }
