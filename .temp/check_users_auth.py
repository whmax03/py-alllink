# -*- coding: utf-8 -*-
"""只读诊断：检查本地 .env 指向的数据库中 users 表的账号与密码哈希格式
不修改任何数据；不输出连接串/密码/完整哈希。
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import urlparse

load_dotenv(os.path.join(BASE, ".env"))

url = os.getenv("DATABASE_URL")
if not url:
    print("DATABASE_URL 未配置")
    sys.exit(1)

parsed = urlparse(url.replace("mysql+pymysql://", "mysql://"))
print(f"[连接目标] host: {parsed.hostname.split('.')[0]}***  库名: {parsed.path.strip('/')}")

engine = create_engine(url)
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    print(f"\n[users 表] 共 {total} 个账号：")

    rows = conn.execute(text(
        "SELECT id, name, email, LENGTH(password_hash) AS hash_len, "
        "LEFT(password_hash, 4) AS hash_prefix "
        "FROM users ORDER BY id"
    )).fetchall()

    for r in rows:
        prefix = (r[4] or "")
        fmt = "bcrypt($2*)格式" if prefix.startswith("$2") else ("无哈希(空)" if r[3] in (0, None) else "非bcrypt格式!")
        print(f"  id={r[0]}  name={r[1]!r}  email={r[2]!r}  hash_len={r[3]}  prefix={prefix!r}  -> {fmt}")

    dup = conn.execute(text(
        "SELECT email, COUNT(*) c FROM users GROUP BY email HAVING c > 1"
    )).fetchall()
    if dup:
        print("\n[警告] 存在重复邮箱行：", [(d[0], d[1]) for d in dup])
    else:
        print("\n[检查] 无重复邮箱行")
