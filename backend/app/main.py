"""FastAPI 入口：原稿编辑、超限分析、求解预览、确认覆盖。

约定：
  * 所有编辑直接落到原稿（SQLite drafts 单行），并使旧预览失效；
  * /api/solve 只生成预览（previews 单行），原稿不动；
  * /api/preview/confirm 在预览仍绑定现行原稿时才用预览覆盖原稿。
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from . import config, db, weave
from .repair import InfeasibleError, solve as repair_solve


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="周期平铺织物组织设计器", lifespan=lifespan)


# ---------------------------------------------------------------- 数据模型

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueIn(StrictModel):
    r: int
    c: int
    value: int


class LockIn(StrictModel):
    r: int
    c: int
    locked: bool


class ResizeIn(StrictModel):
    rows_n: int
    cols_n: int


class KIn(StrictModel):
    k: int


# ---------------------------------------------------------------- 工具

def _state_payload() -> dict:
    draft = db.get_draft()
    analysis = weave.analyze(draft["cells"], draft["max_float"])
    preview = db.get_preview()
    if preview is not None and preview["stale"]:
        preview = None  # 防御：理论上编辑时已清除
    h = db.content_hash(
        draft["rows_n"], draft["cols_n"], draft["cells"],
        draft["locked"], draft["max_float"],
    )
    return {
        "draft": {
            "rows_n": draft["rows_n"],
            "cols_n": draft["cols_n"],
            "cells": draft["cells"],
            "locked": draft["locked"],
            "max_float": draft["max_float"],
            "updated_at": draft["updated_at"],
        },
        "analysis": analysis,
        "preview": preview,
        "hash": h,
        "limits": {
            "max_rows": config.MAX_ROWS,
            "max_cols": config.MAX_COLS,
            "max_k": config.MAX_K,
        },
    }


def _check_index(draft: dict, r: int, c: int) -> None:
    if not (0 <= r < draft["rows_n"] and 0 <= c < draft["cols_n"]):
        raise weave.ValidationError(
            f"编辑越界：({r},{c}) 不在 {draft['rows_n']}x{draft['cols_n']} 矩形内"
        )


def _resize_matrix(matrix, old_r, old_c, new_r, new_c, fill):
    out = [[fill] * new_c for _ in range(new_r)]
    for r in range(min(old_r, new_r)):
        for c in range(min(old_c, new_c)):
            out[r][c] = matrix[r][c]
    return out


# ---------------------------------------------------------------- 接口

@app.get("/api/state")
def read_state():
    return _state_payload()


@app.post("/api/edit/value", status_code=200)
def edit_value(body: ValueIn):
    draft = db.get_draft()
    _check_index(draft, body.r, body.c)
    if body.value not in (0, 1):
        raise weave.ValidationError("格值只能是 0（经在上）或 1（纬在上）")
    if draft["locked"][body.r][body.c]:
        raise weave.ValidationError("该格已锁定，请先解除锁定再改值")
    cells = [row[:] for row in draft["cells"]]
    cells[body.r][body.c] = body.value
    db.save_draft(draft["rows_n"], draft["cols_n"], cells,
                  draft["locked"], draft["max_float"])
    return _state_payload()


@app.post("/api/edit/lock", status_code=200)
def edit_lock(body: LockIn):
    draft = db.get_draft()
    _check_index(draft, body.r, body.c)
    locked = [row[:] for row in draft["locked"]]
    locked[body.r][body.c] = body.locked
    db.save_draft(draft["rows_n"], draft["cols_n"], draft["cells"],
                  locked, draft["max_float"])
    return _state_payload()


@app.post("/api/resize", status_code=200)
def resize(body: ResizeIn):
    weave.validate_dims(body.rows_n, body.cols_n)
    draft = db.get_draft()
    cells = _resize_matrix(
        draft["cells"], draft["rows_n"], draft["cols_n"],
        body.rows_n, body.cols_n, 0)
    locked = _resize_matrix(
        draft["locked"], draft["rows_n"], draft["cols_n"],
        body.rows_n, body.cols_n, False)
    db.save_draft(body.rows_n, body.cols_n, cells, locked,
                  draft["max_float"])
    return _state_payload()


@app.post("/api/k", status_code=200)
def set_k(body: KIn):
    weave.validate_k(body.k)
    draft = db.get_draft()
    db.save_draft(draft["rows_n"], draft["cols_n"], draft["cells"],
                  draft["locked"], body.k)
    return _state_payload()


@app.post("/api/solve", status_code=200)
def solve():
    draft = db.get_draft()
    cells, locked, k = draft["cells"], draft["locked"], draft["max_float"]
    try:
        result = repair_solve(cells, locked, k)
    except InfeasibleError as exc:
        # 无可行修补：保留原稿、不留预览，明确报无解
        db.clear_previews()
        return JSONResponse(
            status_code=422,
            content={
                "infeasible": True,
                "detail": str(exc),
                "state": _state_payload(),
            },
        )

    base_hash = db.content_hash(
        draft["rows_n"], draft["cols_n"], cells, locked, k)
    db.save_preview(
        result["cells"], result["flips"], result["flips_count"],
        base_hash, draft["updated_at"])
    return _state_payload()


@app.post("/api/preview/confirm", status_code=200)
def confirm_preview():
    preview = db.get_preview()
    if preview is None:
        raise weave.ValidationError("当前没有有效预览，请先求解生成预览")
    try:
        db.commit_preview(
            preview["cells"], preview["flips"], preview["flips_count"],
            preview["base_hash"], preview["base_updated"],
        )
    except db.PreviewStaleError:
        return JSONResponse(
            status_code=409,
            content={"detail": "原稿在预览之后发生过变动，该预览已失效，请重新求解"},
        )
    return _state_payload()


@app.exception_handler(weave.ValidationError)
def validation_handler(request, exc: weave.ValidationError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------- 静态站点

DIST = Path(os.getenv("WEAVE_FRONTEND_DIST", "/app/frontend/dist"))
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
