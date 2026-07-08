"""测试 SQLAlchemy 数据库连接"""
from models import SessionLocal, Device

try:
    with SessionLocal() as db:
        count = db.query(Device).count()
        print(f"DB连接成功! 设备数: {count}")
except Exception as e:
    print(f"DB连接失败: {e}")
