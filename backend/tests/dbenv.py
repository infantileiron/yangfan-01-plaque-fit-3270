"""数据库测试共享环境：在导入 src 之前指向临时 SQLite 与产物目录。"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="leiye-test-"), "test.db"))
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ARTIFACTS_DIR", tempfile.mkdtemp(prefix="leiye-artifacts-"))
