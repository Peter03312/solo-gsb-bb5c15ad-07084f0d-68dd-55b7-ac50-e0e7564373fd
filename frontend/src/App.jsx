import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import WeaveGrid from "./WeaveGrid.jsx";

function segmentLabel(seg) {
  const where =
    seg.type === "row" || seg.type === "infinite_row"
      ? `第 ${seg.index} 行`
      : `第 ${seg.index} 列`;
  if (seg.type.startsWith("infinite")) {
    return `${where}：全同 ${seg.value}，平铺后为无限浮长`;
  }
  const kind = seg.type === "row" ? "横向" : "纵向";
  return `${where}：${kind}连续 ${seg.length} 个 ${seg.value}，超过 K`;
}

export default function App() {
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("value"); // value=左键改值 / lock=左键改锁定
  const [rowsInput, setRowsInput] = useState("");
  const [colsInput, setColsInput] = useState("");
  const [kInput, setKInput] = useState("");
  const timer = useRef(null);

  const flash = (msg, isError = false) => {
    if (isError) setError(msg);
    else setNotice(msg);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setError("");
      setNotice("");
    }, 3500);
  };

  const load = useCallback(async () => {
    try {
      setState(await api.state());
    } catch (e) {
      flash(e.message, true);
    }
  }, []);

  useEffect(() => {
    load();
    return () => clearTimeout(timer.current);
  }, [load]);

  // 所有写操作统一入口：后端会做尺寸/格值/K/越界校验并返回最新状态
  const run = useCallback(
    async (fn, okMsg) => {
      setBusy(true);
      setError("");
      try {
        const next = await fn();
        setState(next);
        if (okMsg) setNotice(okMsg);
        return next;
      } catch (e) {
        flash(e.message, true);
        if (e.payload && e.payload.state) setState(e.payload.state);
      } finally {
        setBusy(false);
      }
    },
    []
  );

  if (!state) {
    return <div className="loading">正在加载设计稿…</div>;
  }

  const { draft, analysis, preview, limits } = state;

  const toggleValue = (r, c) => {
    if (mode === "lock") return toggleLock(r, c);
    const nextVal = draft.cells[r][c] === 0 ? 1 : 0;
    run(
      () => api.setValue(r, c, nextVal),
      preview ? "已修改原稿，旧预览已失效。" : ""
    );
  };

  const toggleLock = (r, c) =>
    run(
      () => api.setLock(r, c, !draft.locked[r][c]),
      preview ? "锁定状态已变更，旧预览已失效。" : ""
    );

  const onSolve = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await api.solve();
      setState(next);
      const cnt = next.preview.flips_count;
      setNotice(
        cnt === 0
          ? "原稿已满足全部浮长约束，无需翻转。"
          : `求解完成：最少翻转 ${cnt} 格（同为最优时取字典序最小方案）。`
      );
    } catch (e) {
      if (e.status === 422 && e.payload && e.payload.infeasible) {
        setState(e.payload.state);
        flash("无可行修补：在当前锁定格与 K 下无法满足约束，原稿已保留。", true);
      } else {
        flash(e.message, true);
      }
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = () =>
    run(async () => {
      const next = await api.confirm();
      setNotice("已确认：修补预览覆盖原稿，锁定状态与 K 保持不变。");
      return next;
    });

  const onResize = () =>
    run(async () => {
      const rn = Number(rowsInput);
      const cn = Number(colsInput);
      if (!Number.isInteger(rn) || !Number.isInteger(cn)) {
        throw new Error("行列数必须为整数");
      }
      setRowsInput("");
      setColsInput("");
      return api.resize(rn, cn);
    }, preview ? "尺寸已调整，旧预览已失效。" : "尺寸已调整。");

  const onSetK = () =>
    run(async () => {
      const k = Number(kInput);
      if (!Number.isInteger(k)) throw new Error("K 必须为正整数");
      setKInput("");
      return api.setK(k);
    }, preview ? "K 已变更，旧预览已失效。" : "K 已更新。");

  return (
    <div className="app">
      <header>
        <h1>周期平铺织物组织设计器</h1>
        <p className="subtitle">
          交织周期在左右、上下方向平铺拼接；格值 <b>0</b>＝经线在上，
          <b>1</b>＝纬线在上。任何同值连续段长度不得超过 K，全同行/列为无限浮长。
        </p>
      </header>

      {(error || notice) && (
        <div className={`banner ${error ? "error" : "ok"}`}>
          {error || notice}
        </div>
      )}

      <section className="toolbar">
        <div className="control">
          <label>最大浮长 K＝</label>
          <span className="k-current">{draft.max_float}</span>
          <input
            type="number"
            min="1"
            max={limits.max_k}
            placeholder="新 K"
            value={kInput}
            onChange={(e) => setKInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSetK()}
          />
          <button onClick={onSetK} disabled={busy || kInput === ""}>
            更新 K
          </button>
        </div>

        <div className="control">
          <label>尺寸（≤{limits.max_cols} 列 × {limits.max_rows} 行）</label>
          <input
            type="number"
            min="1"
            max={limits.max_cols}
            placeholder="列"
            value={colsInput}
            onChange={(e) => setColsInput(e.target.value)}
          />
          <input
            type="number"
            min="1"
            max={limits.max_rows}
            placeholder="行"
            value={rowsInput}
            onChange={(e) => setRowsInput(e.target.value)}
          />
          <button
            onClick={onResize}
            disabled={busy || rowsInput === "" || colsInput === ""}
          >
            调整尺寸
          </button>
          <span className="hint">新区域以 0、未锁定填充</span>
        </div>

        <div className="control">
          <label>左键动作：</label>
          <label className="radio">
            <input
              type="radio"
              checked={mode === "value"}
              onChange={() => setMode("value")}
            />
            翻转 0/1
          </label>
          <label className="radio">
            <input
              type="radio"
              checked={mode === "lock"}
              onChange={() => setMode("lock")}
            />
            切换锁定
          </label>
          <span className="hint">（任何模式下都可用鼠标右键切换锁定）</span>
        </div>
      </section>

      <main className="panels">
        <section className="panel">
          <h2>原稿（当前设计稿）</h2>
          <p className="panel-meta">
            {draft.cols_n} 列 × {draft.rows_n} 行　·　K＝{draft.max_float}　·
            {analysis.valid ? (
              <span className="valid">全部浮长合法 ✓</span>
            ) : (
              <span className="invalid">
                {analysis.segments.length} 处超限（红色标出）
              </span>
            )}
          </p>
          <WeaveGrid
            rows_n={draft.rows_n}
            cols_n={draft.cols_n}
            cells={draft.cells}
            locked={draft.locked}
            violatingCells={analysis.violating_cells}
            mode="edit"
            busy={busy}
            onToggleValue={toggleValue}
            onToggleLock={toggleLock}
          />
          <ul className="legend">
            <li><span className="sw v0" /> 0 经在上</li>
            <li><span className="sw v1" /> 1 纬在上</li>
            <li><span className="sw violating" /> 超限段</li>
            <li><span className="sw locked" /> 锁定格 🔒</li>
          </ul>

          {analysis.segments.length > 0 && (
            <div className="seg-list">
              <h3>超限连续段</h3>
              <ul>
                {analysis.segments.map((s, i) => (
                  <li key={i}>{segmentLabel(s)}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="actions">
            <button className="primary" onClick={onSolve} disabled={busy}>
              {busy ? "求解中…" : "求解最少翻转修补"}
            </button>
            <span className="hint">
              目标：翻转未锁定格数最少；同数取行展开字典序最小。
            </span>
          </div>
        </section>

        <section className="panel preview-panel">
          <h2>修补预览</h2>
          {preview ? (
            <>
              <p className="panel-meta">
                最少翻转 <b>{preview.flips_count}</b> 格，
                位置：
                {preview.flips.length === 0
                  ? "无（原稿即最优）"
                  : preview.flips
                      .map(([r, c]) => `(${r},${c})`)
                      .join("、")}
              </p>
              <WeaveGrid
                rows_n={draft.rows_n}
                cols_n={draft.cols_n}
                cells={preview.cells}
                locked={draft.locked}
                violatingCells={[]}
                flipCells={preview.flips}
                mode="preview"
              />
              <p className="hint">
                金色 ↔ 标出翻转位置；锁定格在修补中保持不变。
              </p>
              <div className="actions">
                <button className="primary" onClick={onConfirm} disabled={busy}>
                  确认：用预览覆盖原稿
                </button>
                <span className="hint warn">
                  确认前对原稿的任何编辑都会使本预览失效；确认后后续操作基于新原稿。
                </span>
              </div>
            </>
          ) : (
            <p className="empty">
              尚无预览。点击左侧“求解最少翻转修补”；若无可行修补，将保留原稿并提示无解。
            </p>
          )}
        </section>
      </main>

      <footer>
        <span>
          更新时间 {new Date(draft.updated_at).toLocaleString("zh-CN")} ·
          原稿指纹 {state.hash.slice(0, 10)}…
        </span>
      </footer>
    </div>
  );
}
