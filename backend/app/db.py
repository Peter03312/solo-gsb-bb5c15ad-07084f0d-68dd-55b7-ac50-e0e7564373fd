"""SQLite 访问层：原稿单行 + 预览单行。

应用启动时建表并在空库中写入示例稿；预览通过 (base_hash, base_updated)
双重指纹与原稿绑定，原稿任何变动都会使旧预览失效。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def content_hash(rows_n: int, cols_n: int, cells, locked, k: int) -> str:
    payload = json.dumps(
        {"r": rows_n, "c": cols_n, "cells": cells, "locked": locked, "k": k},
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# 首次启动的示例稿：4x4，K=2。
# 第 1、2 列各含一个跨上下边界的 3 连段（标红的超限段）；(0,0) 锁定。
# 最少 2 次翻转（(0,1)、(0,2)）即可修补。
SEED = {
    "rows_n": 4,
    "cols_n": 4,
    "cells": [
        [0, 1, 0, 1],
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [1, 1, 0, 0],
    ],
    "locked": [
        [True, False, False, False],
        [False, False, False, False],
        [False, False, False, False],
        [False, False, False, False],
    ],
    "max_float": 2,
}


def init_db() -> None:
    db = Path(config.DB_PATH)
    db.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(config.SCHEMA_PATH).read_text(encoding="utf-8")
    with sqlite3.connect(db) as conn:
        conn.executescript(schema)
        row = conn.execute("SELECT COUNT(*) FROM drafts WHERE id = 1").fetchone()
        if row[0] == 0:
            conn.execute(
                "INSERT INTO drafts (id, rows_n, cols_n, cells, locked, "
                "max_float, updated_at) VALUES (1, ?, ?, ?, ?, ?, ?)",
                (
                    SEED["rows_n"],
                    SEED["cols_n"],
                    json.dumps(SEED["cells"]),
                    json.dumps(SEED["locked"]),
                    SEED["max_float"],
                    _now(),
                ),
            )
        conn.commit()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_draft() -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE id = 1").fetchone()
    return _draft_row(row)


def _draft_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "rows_n": row["rows_n"],
        "cols_n": row["cols_n"],
        "cells": json.loads(row["cells"]),
        "locked": json.loads(row["locked"]),
        "max_float": row["max_float"],
        "updated_at": row["updated_at"],
    }


def save_draft(rows_n: int, cols_n: int, cells, locked, k: int) -> dict[str, Any]:
    ts = _now()
    with _connect() as conn:
        conn.execute(
            "UPDATE drafts SET rows_n = ?, cols_n = ?, cells = ?, locked = ?, "
            "max_float = ?, updated_at = ? WHERE id = 1",
            (rows_n, cols_n, json.dumps(cells), json.dumps(locked), k, ts),
        )
        # 原稿变动：旧预览立即失效
        conn.execute("DELETE FROM previews")
        conn.commit()
    return get_draft()


def commit_preview(cells, flips, flips_count: int, base_hash: str,
                   base_updated: str) -> dict[str, Any]:
    """确认当前预览：仅当预览仍绑定现行原稿时才覆盖原稿。"""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE id = 1").fetchone()
        draft = _draft_row(row)
        current_hash = content_hash(
            draft["rows_n"], draft["cols_n"], draft["cells"],
            draft["locked"], draft["max_float"],
        )
        if current_hash != base_hash or draft["updated_at"] != base_updated:
            raise PreviewStaleError
        ts = _now()
        conn.execute(
            "UPDATE drafts SET cells = ?, updated_at = ? WHERE id = 1",
            (json.dumps(cells), ts),
        )
        conn.execute("DELETE FROM previews")
        conn.commit()
    return get_draft()


class PreviewStaleError(Exception):
    """预览对应的原稿已被修改，确认被拒绝。"""


def clear_previews() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM previews")
        conn.commit()


def save_preview(cells, flips, flips_count: int, base_hash: str,
                 base_updated: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM previews")
        conn.execute(
            "INSERT INTO previews (id, cells, flips, flips_count, base_hash, "
            "base_updated, created_at) VALUES (1, ?, ?, ?, ?, ?, ?)",
            (json.dumps(cells), json.dumps(flips), flips_count,
             base_hash, base_updated, _now()),
        )
        conn.commit()


def get_preview() -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM previews WHERE id = 1").fetchone()
        if row is None:
            return None
        draft_row = conn.execute(
            "SELECT updated_at FROM drafts WHERE id = 1").fetchone()
    base_hash = row["base_hash"]
    base_updated = row["base_updated"]
    return {
        "cells": json.loads(row["cells"]),
        "flips": json.loads(row["flips"]),
        "flips_count": row["flips_count"],
        "base_hash": base_hash,
        "base_updated": base_updated,
        "stale": draft_row["updated_at"] != base_updated,
    }
