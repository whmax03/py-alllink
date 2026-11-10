from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import engine, Base
from app.routers import users, sellfox, inventory, auth
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

# 注册 CORS 中间件（必须放在 UnifiedResponseMiddleware 之前，否则跨域预检请求会被拦截）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://keen-douhua-7da648.netlify.app",  # 生产前端
        "http://localhost:3000",                     # 本地前端开发
        "http://localhost:5173",                     # Vite 本地开发
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册全局统一响应中间件
app.add_middleware(UnifiedResponseMiddleware)

# 注册全局异常处理器
register_exception_handlers(app)

# 注册路由
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sellfox.router)
app.include_router(inventory.router)

@app.get("/")
def root():
    return {"message": "Welcome to FastAPI backend powered by Supabase!"}
