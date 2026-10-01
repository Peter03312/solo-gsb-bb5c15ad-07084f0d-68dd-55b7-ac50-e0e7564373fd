"""最小修补精确求解器。

模型（网格在水平/垂直方向均为环面）：
  变量 y_{r,c} ∈ {0,1}            —— 修补后的格值
  锁定格：y 固定为原值
  每个长度 K+1 的环面窗口（行内/列内）内至少出现一个 0 和一个 1
       ⇔ 该周期方向上不存在长度 > K 的同值连续段
       ⇔ 全同线（无限浮长）也被禁止（此时窗口退化为整条线）

两级目标：
  1) 翻转的未锁定格数量最少（整数线性规划，HiGHS）
  2) 同数时取按行展开字典序最小的格值序列：
     把行优先比特流每 CHUNK_BITS 位作为一个二进制数，
     在固定前块的前提下逐块最小化（每块一次极小求解）。

规模上限 16x8=128 个 0/1 变量，HiGHS 可瞬时求解。
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import milp
from scipy.sparse import coo_matrix, vstack

from .weave import analyze

CHUNK_BITS = 20  # 单块权重最大 2^20，浮点表示精确，round 无歧义


class InfeasibleError(Exception):
    """不存在满足浮长约束且尊重锁定格的修补。"""


def _window_constraints(rows_n: int, cols_n: int, k: int, idx: dict):
    """构造“每个长度 K+1 的环面窗口同时含 0 与 1”的线性约束。

    对窗口格集合 S（|S|=w）：1 <= Σ_S y <= w-1
    转为  A y <= w-1 与  -A y <= -1。
    窗口退化为整条线（w=线长）时只取一个起点，各起点等价。
    """
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    ub: list[float] = []
    row_id = 0

    def add_window(members: list[tuple[int, int]], w: int):
        nonlocal row_id
        for (r, c) in members:
            rows.append(row_id)
            cols.append(idx[(r, c)])
            data.append(1.0)
        ub.append(float(w - 1))
        row_id += 1
        for (r, c) in members:
            rows.append(row_id)
            cols.append(idx[(r, c)])
            data.append(-1.0)
        ub.append(-1.0)
        row_id += 1

    w = min(k + 1, cols_n)
    starts = range(1) if w == cols_n else range(cols_n)
    for r in range(rows_n):
        for s in starts:
            add_window([(r, (s + t) % cols_n) for t in range(w)], w)

    w = min(k + 1, rows_n)
    starts = range(1) if w == rows_n else range(rows_n)
    for c in range(cols_n):
        for s in starts:
            add_window([((s + t) % rows_n, c) for t in range(w)], w)

    a = coo_matrix((data, (rows, cols)), shape=(row_id, rows_n * cols_n)).tocsr()
    return a, np.array(ub, dtype=float)


def solve(cells: list[list[int]], locked: list[list[bool]], k: int) -> dict:
    rows_n, cols_n = len(cells), len(cells[0])
    n = rows_n * cols_n
    pos = [(r, c) for r in range(rows_n) for c in range(cols_n)]
    idx = {(r, c): r * cols_n + c for (r, c) in pos}

    a_win, ub_win = _window_constraints(rows_n, cols_n, k, idx)
    unlock = [p for p in pos if not locked[p[0]][p[1]]]

    lb = np.zeros(n)
    ub = np.ones(n)
    for (r, c) in pos:
        if locked[r][c]:
            lb[idx[(r, c)]] = ub[idx[(r, c)]] = float(cells[r][c])
    integrality = np.ones(n)

    def run(cost: np.ndarray, extra_a, extra_ub):
        from scipy.optimize import LinearConstraint
        if extra_a is not None:
            a = vstack([a_win, extra_a], format="csr")
            b = np.concatenate([ub_win, extra_ub])
        else:
            a, b = a_win, ub_win
        lower = np.full(a.shape[0], -np.inf)
        result = milp(
            c=cost,
            integrality=integrality,
            bounds=(lb, ub),
            constraints=LinearConstraint(a, lower, b),
            options={"disp": False, "mip_rel_gap": 0.0, "time_limit": 60},
        )
        if result.status != 0 or result.x is None:
            return None, result
        return np.rint(result.x).astype(int), result

    # —— 第一级：最少翻转数 ——
    # 翻转代价 y!=o：o=0 时为 y，o=1 时为 1-y；线性化后常数为未锁定 1 的个数。
    cost1 = np.zeros(n)
    ones_unlocked = 0
    for (r, c) in unlock:
        cost1[idx[(r, c)]] = 1.0 - 2.0 * cells[r][c]
        ones_unlocked += cells[r][c]
    y1, res1 = run(cost1, None, None)
    if y1 is None:
        raise InfeasibleError("不存在满足浮长约束且尊重锁定格的修补方案")
    min_flips = int(round(res1.fun)) + ones_unlocked

    # 翻转数固定：Σ_unlocked (1-2o)·y = L - Σ_unlocked o
    eq_data = [float(1 - 2 * cells[r][c]) for (r, c) in unlock]
    flip_eq = coo_matrix(
        (eq_data, ([0] * len(unlock), [idx[p] for p in unlock])),
        shape=(1, n),
    ).tocsr()
    flip_ub = np.array([float(min_flips - ones_unlocked)])

    # —— 第二级：行优先字典序最小，按 CHUNK_BITS 位分块逐块最小化 ——
    chosen: dict[tuple[int, int], int] = {}
    for start in range(0, n, CHUNK_BITS):
        block = pos[start:start + CHUNK_BITS]
        cost = np.zeros(n)
        for i, p in enumerate(block):
            cost[idx[p]] = float(1 << (len(block) - 1 - i))  # 行优先靠前=高位

        extras = [flip_eq]
        extra_ubs = [flip_ub]
        if chosen:
            fr, fc, fd = [], [], []
            fub: list[float] = []
            fid = 0
            for (p, val) in chosen.items():
                j = idx[p]
                fr += [fid, fid + 1]
                fc += [j, j]
                fd += [1.0, -1.0]
                fub += [float(val), float(-val)]
                fid += 2
            extras.append(coo_matrix((fd, (fr, fc)), shape=(fid, n)).tocsr())
            extra_ubs.append(np.array(fub))

        yb, _ = run(cost, vstack(extras, format="csr"), np.concatenate(extra_ubs))
        if yb is None:
            raise InfeasibleError("字典序优化阶段求解失败（不应发生，请重试）")
        for p in block:
            chosen[p] = int(yb[idx[p]])

    patched = [[0] * cols_n for _ in range(rows_n)]
    flips: list[list[int]] = []
    for (r, c) in pos:
        v = chosen[(r, c)]
        patched[r][c] = v
        if not locked[r][c] and v != cells[r][c]:
            flips.append([r, c])

    # 防御性校验
    for (r, c) in pos:
        if locked[r][c] and patched[r][c] != cells[r][c]:
            raise RuntimeError("内部错误：求解改动了锁定格")
    if len(flips) != min_flips:
        raise RuntimeError("内部错误：翻转数与最优值不符")
    if not analyze(patched, k)["valid"]:
        raise RuntimeError("内部错误：修补结果仍超限")

    return {
        "cells": patched,
        "flips": flips,
        "flips_count": min_flips,
    }
