"""交织格校验与周期（环面）连续段分析。

一个设计周期在水平方向左右拼接、垂直方向上下拼接。
因此行的连续段按列下标取模延伸，列同理。
全同的一行/一列在平铺后连成无限长浮长。
"""
from __future__ import annotations

from . import config


class ValidationError(ValueError):
    """尺寸、格值、K 等不合法时抛出，映射为 HTTP 400。"""


def validate_dims(rows_n: int, cols_n: int) -> None:
    if not isinstance(rows_n, int) or not isinstance(cols_n, int):
        raise ValidationError("行列数必须为整数")
    if rows_n < 1 or cols_n < 1:
        raise ValidationError("交织格不能为空矩形，行列数至少为 1")
    if rows_n > config.MAX_ROWS or cols_n > config.MAX_COLS:
        raise ValidationError(
            f"尺寸越界：至多 {config.MAX_COLS} 列、{config.MAX_ROWS} 行"
        )


def validate_k(k) -> None:
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValidationError("最大浮长 K 必须为正整数")
    if k > config.MAX_K:
        raise ValidationError(f"K 过大（上限 {config.MAX_K}）")


def validate_matrix(matrix, rows_n: int, cols_n: int, name: str = "交织格") -> None:
    if not isinstance(matrix, list) or len(matrix) != rows_n:
        raise ValidationError(f"{name}行数与尺寸不符")
    for row in matrix:
        if not isinstance(row, list) or len(row) != cols_n:
            raise ValidationError(f"{name}必须为 {rows_n}x{cols_n} 的矩形")
        for v in row:
            if not isinstance(v, int) or isinstance(v, bool) or v not in (0, 1):
                raise ValidationError(f"{name}格值只能是 0 或 1")


def validate_locked(locked, rows_n: int, cols_n: int) -> None:
    if not isinstance(locked, list) or len(locked) != rows_n:
        raise ValidationError("锁定格行数与尺寸不符")
    for row in locked:
        if not isinstance(row, list) or len(row) != cols_n:
            raise ValidationError(f"锁定格必须为 {rows_n}x{cols_n} 的矩形")
        for v in row:
            if not isinstance(v, bool):
                raise ValidationError("锁定格只能为 true/false")


def validate_state(rows_n: int, cols_n: int, cells, locked, k: int) -> None:
    validate_dims(rows_n, cols_n)
    validate_matrix(cells, rows_n, cols_n, "交织格")
    validate_locked(locked, rows_n, cols_n)
    validate_k(k)


def cyclic_segments(line: list[int]) -> list[dict]:
    """把一条环面序列切成同值连续段。

    返回 [{value, length, start, end}]，start/end 为序列内下标（左闭右开，
    跨拼接边界的段起点可能大于终点）。全同序列返回单段且 uniform=True。
    """
    n = len(line)
    change = [i for i in range(n) if line[i] != line[(i - 1) % n]]
    if not change:
        return [{"value": line[0], "length": n, "start": 0, "end": 0, "uniform": True}]
    segments = []
    for idx, start in enumerate(change):
        end = change[(idx + 1) % len(change)]
        length = (end - start) % n
        segments.append(
            {"value": line[start], "length": length, "start": start, "end": end,
             "uniform": False}
        )
    return segments


def segment_cells(r: int | None, c: int | None, seg: dict, n: int,
                  vertical: bool) -> list[list[int]]:
    """展开一个连续段覆盖的格坐标（含跨拼接边界的环绕）。"""
    length, start = seg["length"], seg["start"]
    out = []
    for t in range(length):
        idx = (start + t) % n
        out.append([idx, c] if vertical else [r, idx])
    return out


def analyze(cells: list[list[int]], k: int) -> dict:
    """标出原稿中所有超出 K 的连续段（含无限浮长行/列）。

    violating_cells 为所有越界格的去重下标集合；segments 给出每段详情。
    """
    rows_n, cols_n = len(cells), len(cells[0])
    segments: list[dict] = []
    violating: set[tuple[int, int]] = set()

    for r in range(rows_n):
        for seg in cyclic_segments(cells[r]):
            if seg["uniform"]:
                kind = "infinite_row"
                bad = True
            elif seg["length"] > k:
                kind = "row"
                bad = True
            else:
                continue
            coords = segment_cells(r, None, seg, cols_n, False)
            if bad:
                violating.update(map(tuple, coords))
            segments.append({
                "type": kind,
                "index": r,
                "value": seg["value"],
                "length": None if seg["uniform"] else seg["length"],
                "start": seg["start"],
                "end": seg["end"],
                "cells": coords,
            })

    for c in range(cols_n):
        col = [cells[r][c] for r in range(rows_n)]
        for seg in cyclic_segments(col):
            if seg["uniform"]:
                kind = "infinite_col"
            elif seg["length"] > k:
                kind = "col"
            else:
                continue
            coords = segment_cells(None, c, seg, rows_n, True)
            violating.update(map(tuple, coords))
            segments.append({
                "type": kind,
                "index": c,
                "value": seg["value"],
                "length": None if seg["uniform"] else seg["length"],
                "start": seg["start"],
                "end": seg["end"],
                "cells": coords,
            })

    return {
        "segments": segments,
        "violating_cells": sorted(map(list, violating)),
        "valid": len(segments) == 0,
    }
