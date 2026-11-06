from fastapi import FastAPI
from app.database import engine, Base
from app.routers import users, sellfox, inventory
from app.core.response import UnifiedResponseMiddleware, register_exception_handlers

# 导入模型确保建表
from app.models import user, inventory as inventory_models

# 自动在 Supabase 中创建表结构（如果表已存在则会跳过）
Base.metadata.create_all(bind=engine)
from app.core.sellfox_client import sellfox_token_manager


app = FastAPI(
    title="FastAPI + Supabase Production Project",
    description="一个基于 FastAPI 规范分层并连接 Supabase 的现代化后端模版",
    version="1.0.0"
)

# 注册全局统一响应中间件
app.add_middleware(UnifiedResponseMiddleware)

# 注册全局异常处理器
register_exception_handlers(app)

# 注册路由
app.include_router(users.router)
app.include_router(sellfox.router)
app.include_router(inventory.router)

@app.get("/")
def root():
    return {"message": "Welcome to FastAPI backend powered by Supabase!"}
