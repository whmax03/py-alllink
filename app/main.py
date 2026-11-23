from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import engine, Base, SessionLocal
from app.routers import users, sellfox, inventory, auth, rbac
from app.core.response import UnifiedResponseMiddleware, register_exception_handlers

# 导入模型确保建表
from app.models import user, inventory as inventory_models, rbac as rbac_models

# 自动创建表结构（如果表已存在则会跳过）
Base.metadata.create_all(bind=engine)
from app.core.sellfox_client import sellfox_token_manager

# ---------- 初始化默认角色和权限 ----------
def init_default_data():
    """首次启动时创建默认 admin 角色和基础权限"""
    db = SessionLocal()
    try:
        # 创建 admin 角色（如果不存在）
        from app.models.rbac import Role, Permission
        admin = db.query(Role).filter(Role.code == "admin").first()
        if not admin:
            admin = Role(name="管理员", code="admin", description="系统管理员，拥有所有权限")
            db.add(admin)
            db.commit()
            db.refresh(admin)

        # 创建 viewer 角色
        viewer = db.query(Role).filter(Role.code == "viewer").first()
        if not viewer:
            viewer = Role(name="查看者", code="viewer", description="只读用户")
            db.add(viewer)
            db.commit()
            db.refresh(viewer)

        # 创建默认权限（如果不存在）
        default_permissions = [
            # 页面权限
            {"name": "国内仓库存页面", "code": "page:inventory:domestic", "type": "page"},
            {"name": "海外仓库存页面", "code": "page:inventory:overseas", "type": "page"},
            {"name": "转运库存页面", "code": "page:inventory:transit", "type": "page"},
            {"name": "用户管理页面", "code": "page:users", "type": "page"},
            {"name": "权限管理页面", "code": "page:rbac", "type": "page"},
            # Tab 显示权限
            {"name": "国内仓Tab", "code": "tab:domestic", "type": "tab"},
            {"name": "海外仓Tab", "code": "tab:overseas", "type": "tab"},
            {"name": "转运库存Tab", "code": "tab:transit", "type": "tab"},
            {"name": "转运明细Tab", "code": "tab:transit_detail", "type": "tab"},
            # 平台权限（控制角色可查看的数据平台，与库存页筛选平台一致）
            {"name": "金蝶平台", "code": "platform:金蝶", "type": "platform"},
            {"name": "澳霖平台", "code": "platform:澳霖", "type": "platform"},
            {"name": "亚马逊平台", "code": "platform:亚马逊", "type": "platform"},
            {"name": "eBay平台", "code": "platform:eBay", "type": "platform"},
            {"name": "Shopee平台", "code": "platform:Shopee", "type": "platform"},
            {"name": "Tiktok平台", "code": "platform:Tiktok", "type": "platform"},
            # 数据权限
            {"name": "导入数据权限", "code": "data:import", "type": "data"},
            {"name": "导出数据权限", "code": "data:export", "type": "data"},
        ]

        for p in default_permissions:
            existing = db.query(Permission).filter(Permission.code == p["code"]).first()
            if not existing:
                db.add(Permission(
                    name=p["name"],
                    code=p["code"],
                    type=p["type"],
                ))
        db.commit()

    finally:
        db.close()

init_default_data()


app = FastAPI(
    title="AllLink 后端服务",
    description="FastAPI + MySQL + RBAC 权限系统 + 多仓库库存管理",
    version="2.0.0"
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
app.include_router(rbac.router)
app.include_router(sellfox.router)
app.include_router(inventory.router)

@app.get("/")
def root():
    return {"message": "Welcome to AllLink Backend v2.0"}
