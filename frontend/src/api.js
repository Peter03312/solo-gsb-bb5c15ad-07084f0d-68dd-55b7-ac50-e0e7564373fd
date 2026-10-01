// 后端 API 封装：统一错误提示，返回最新全局状态
async function call(path, body) {
  const opts = body === undefined
    ? { method: "GET" }
    : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      };
  const res = await fetch(path, opts);
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* 非 JSON 响应 */
  }
  if (!res.ok) {
    const err = new Error((data && data.detail) || `请求失败（${res.status}）`);
    err.status = res.status;
    err.payload = data;
    throw err;
  }
  return data;
}

export const api = {
  state: () => call("/api/state"),
  setValue: (r, c, value) => call("/api/edit/value", { r, c, value }),
  setLock: (r, c, locked) => call("/api/edit/lock", { r, c, locked }),
  resize: (rows_n, cols_n) => call("/api/resize", { rows_n, cols_n }),
  setK: (k) => call("/api/k", { k }),
  solve: () => call("/api/solve"),
  confirm: () => call("/api/preview/confirm"),
};
