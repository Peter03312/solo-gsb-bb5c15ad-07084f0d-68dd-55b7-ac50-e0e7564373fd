-- 周期平铺织物组织设计器：数据库结构
-- 原稿（设计稿）与当前预览各占一行；预览在原稿变动后失效。

CREATE TABLE IF NOT EXISTS drafts (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    rows_n    INTEGER NOT NULL,
    cols_n    INTEGER NOT NULL,
    cells     TEXT    NOT NULL,   -- JSON，rows_n x cols_n，元素为 0(经在上)/1(纬在上)
    locked    TEXT    NOT NULL,   -- JSON，rows_n x cols_n，true 表示锁定格
    max_float INTEGER NOT NULL,   -- 最大允许浮长 K（正整数）
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS previews (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    cells        TEXT    NOT NULL,  -- JSON，修补后的格值
    flips        TEXT    NOT NULL,  -- JSON，翻转位置 [[r,c],...]
    flips_count  INTEGER NOT NULL,
    base_hash    TEXT    NOT NULL,  -- 生成预览时原稿的内容指纹
    base_updated TEXT    NOT NULL,  -- 生成预览时原稿的更新时间
    created_at   TEXT    NOT NULL
);
