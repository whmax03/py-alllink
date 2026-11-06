# FastAPI + Supabase Demo uvicorn app.main:app --reload

一个基于 FastAPI 规范分层并连接 Supabase (PostgreSQL) 的现代化后端模版。

## 项目结构

```
fastapi_supabase_demo/
│
├── app/
│   ├── __init__.py
│   ├── main.py          # 主入口文件
│   ├── database.py      # Supabase 数据库连接配置
│   ├── models/          # 数据库表结构模型 (SQLAlchemy)
│   │   ├── __init__.py
│   │   └── user.py
│   ├── schemas/         # 数据校验与传输模型 (Pydantic)
│   │   ├── __init__.py
│   │   └── user.py
│   ├── crud/            # 数据库增删改查操作
│   │   ├── __init__.py
│   │   └── user.py
│   └── routers/         # 接口路由模块
│       ├── __init__.py
│       └── users.py
│
├── .env                 # 环境变量配置文件（存放 Supabase 密钥）
├── requirements.txt     # 依赖包列表
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录下编辑 `.env` 文件，填入你的 Supabase 数据库连接串：

```
DATABASE_URL=postgresql://postgres:[你的数据库密码]@db.[你的项目引用ID].supabase.co:5432/postgres
```

### 3. 启动服务

```bash
uvicorn app.main:app --reload
```

### 4. 访问 API 文档

启动后访问 http://127.0.0.1:8000/docs 查看 Swagger UI 交互式文档。
