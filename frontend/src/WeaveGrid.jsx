import React from "react";

const idx = (r, c) => `${r},${c}`;

/**
 * 交织格编辑/预览组件。
 * mode: "edit" | "preview"
 *  - 编辑模式：左键翻转 0/1，右键切换锁定；红色描边/底色标出超限段
 *  - 预览模式：只展示，翻转位置带金色角标
 */
export default function WeaveGrid({
  rows_n,
  cols_n,
  cells,
  locked,
  violatingCells,
  flipCells = [],
  mode = "edit",
  onToggleValue,
  onToggleLock,
  busy,
}) {
  const violateSet = new Set((violatingCells || []).map(([r, c]) => idx(r, c)));
  const flipSet = new Set((flipCells || []).map(([r, c]) => idx(r, c)));

  return (
    <div className={`grid-wrap mode-${mode}`}>
      <div
        className="grid"
        style={{
          gridTemplateColumns: `24px repeat(${cols_n}, var(--cell-size))`,
        }}
      >
        {/* 角标 */}
        <div className="axis corner">行\列</div>
        {Array.from({ length: cols_n }, (_, c) => (
          <div key={`h${c}`} className="axis col-head">
            {c}
            <span className="wrap-arrow" title="左右拼接边界相连">
              {c === 0 ? "⟲" : ""}
            </span>
          </div>
        ))}

        {Array.from({ length: rows_n }, (_, r) => (
          <React.Fragment key={`row${r}`}>
            <div className="axis row-head">
              {r}
              {r === 0 ? (
                <span className="wrap-arrow v" title="上下拼接边界相连">
                  ⟲
                </span>
              ) : (
                ""
              )}
            </div>
            {Array.from({ length: cols_n }, (_, c) => {
              const v = cells[r][c];
              const isLock = locked[r][c];
              const bad = violateSet.has(idx(r, c));
              const flip = flipSet.has(idx(r, c));
              const cls = [
                "cell",
                v === 1 ? "v1" : "v0",
                isLock ? "locked" : "",
                bad ? "violating" : "",
                flip ? "flip" : "",
                mode === "preview" ? "readonly" : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <button
                  key={idx(r, c)}
                  type="button"
                  className={cls}
                  disabled={busy || mode === "preview"}
                  title={
                    `第${r}行 第${c}列：${v === 1 ? "纬在上(1)" : "经在上(0)"}` +
                    (isLock ? "，已锁定" : "") +
                    (bad ? "，属于超限连续段" : "") +
                    (mode === "edit" ? "\n左键：翻转值　右键：切换锁定" : "")
                  }
                  onClick={() => onToggleValue && onToggleValue(r, c)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (mode === "edit" && onToggleLock) onToggleLock(r, c);
                  }}
                >
                  {isLock && <span className="lock-badge" title="锁定格">🔒</span>}
                  {flip && <span className="flip-badge" title="此处将翻转">↔</span>}
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </div>
      <p className="wrap-hint">
        ⟲ 网格为平铺周期：最左列与最右列、最上行与最下行在拼接时相连；
        全同行/列为无限浮长。
      </p>
    </div>
  );
}
