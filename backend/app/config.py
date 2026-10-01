"""全局配置：所有数值均可通过环境变量覆盖（见 README）。"""
import os
from pathlib import Path

MAX_ROWS = int(os.getenv("WEAVE_MAX_ROWS", "16"))
MAX_COLS = int(os.getenv("WEAVE_MAX_COLS", "8"))
MAX_K = int(os.getenv("WEAVE_MAX_K", "1000000"))

DB_PATH = Path(os.getenv("WEAVE_DB_PATH", "/data/weave.db"))
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"
