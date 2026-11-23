# -*- coding: utf-8 -*-
"""只读诊断：将用户提供的 bcrypt 哈希与本地库 users 表各账号哈希做相等性比对。
- 不修改任何数据；不输出完整哈希；不做暴力破解，仅哈希相等性比对。
- 相同 bcrypt 哈希 <=> 同一密码 + 同一盐（注册/改密时生成，逐一对应）。
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(BASE, ".env"))

# 用户提供的待比对哈希
TARGET_HASH = "$2b$12$.Z9HHv67hcIgBh1Fg3gFcuT3pukk0vx5TPp9iuH5nNX3Ps5E7aUFS"

url = os.getenv("DATABASE_URL")
if not url:
    print("DATABASE_URL 未配置")
    sys.exit(1)

engine = create_engine(url)
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, name, email, password_hash FROM users ORDER BY id"
    )).fetchall()

    print(f"[比对] 目标哈希(尾6位 …{TARGET_HASH[-6:]}) vs 本地库 {len(rows)} 个账号：")
    matched = None
    for r in rows:
        is_match = (r[3] == TARGET_HASH)
        print(f"  id={r[0]}  name={r[1]!r}  email={r[2]!r}  -> {'✅ 匹配' if is_match else '不匹配'}")
        if is_match:
            matched = r

    if matched:
        print(f"\n[结论] 该哈希属于本地库账号: id={matched[0]}  name={matched[1]}  email={matched[2]}")
    else:
        print("\n[结论] 该哈希不属于本地库任何账号 —— 极可能来自另一套数据库（如线上 Render 后端所连的库），")
        print("       这与上一轮「线上登录报 101」的推断互相印证：线上连的库与本地的 users 数据不同。")
