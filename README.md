# 周期平铺织物组织设计器

一个用于设计 **周期平铺（环面）织物组织** 的网页工具：设计师录入至多
**8 列 × 16 行** 的非空矩形交织格，指定最大浮长 **K** 与锁定格，系统标出
原稿中所有超限连续段，并求出 **翻转未锁定格数量最少** 的可行修补；翻转数
相同时取 **按行展开字典序最小** 的格值序列。修补先出预览，确认后才覆盖原稿。

- 格值：`0`＝经线在上，`1`＝纬线在上
- 每行/每列的同值连续段把 **左右、上下拼接边界** 视为相连（环面周期）
- 全同的一行或一列视为 **无限浮长**，必然超限
- 求解器：0/1 整数规划（SciPy/HiGHS），两级目标精确最优，非启发式
- 后端 FastAPI + SQLite，前端 React + Vite，Docker 多阶段构建一键启动

## 一键启动（推荐）

需要安装 Docker 与 Docker Compose v2。

```bash
docker compose up --build
```

启动后打开：

- **网页地址：<http://localhost:8000>**
- 端口：容器 `8000` → 宿主机默认 `8000`（可用环境变量改，见下）

首次启动会自动建表并写入一份 4×4、K=2 的示例稿（含两处超限段和一个锁定格）。
SQLite 数据库保存在命名卷 `weave-data` 中，容器重启后数据保留；
`docker compose down -v` 会删除数据卷并在下次启动重新初始化。

健康检查：<http://localhost:8000/api/state>（返回当前原稿、超限分析与预览的 JSON）。

## 配置

全部配置通过环境变量提供（见 `docker-compose.yml`，可在仓库根目录放 `.env` 覆盖）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEAVE_PORT` | `8000` | 宿主机映射端口（compose 端口映射） |
| `WEAVE_DB_PATH` | `/data/weave.db` | 容器内 SQLite 文件路径 |
| `WEAVE_MAX_ROWS` | `16` | 最大行数 |
| `WEAVE_MAX_COLS` | `8` | 最大列数 |
| `WEAVE_MAX_K` | `1000000` | K 的上限 |

例如改用 9000 端口：

```bash
WEAVE_PORT=9000 docker compose up --build
# 然后访问 http://localhost:9000
```

## 操作说明

1. **编辑原稿**
   - 左键：按工具条所选动作“翻转 0/1”或“切换锁定”；右键始终切换锁定。
   - 工具条可修改 K、调整尺寸（新区域以 `0`、未锁定填充）。
   - 尺寸必须为 1–8 列、1–16 行的非空矩形；格值只能 0/1；K 为正整数。
   - 锁定格不可直接改值（先解锁）；任何越界/非法操作都会被后端拒绝并提示。
2. **超限标注**：红色格属于长度 > K 的连续段；全同行/列在“超限连续段”
   列表中标为“无限浮长”。
3. **求解预览**：点击“求解最少翻转修补”。右侧显示最少翻转格数、翻转位置
   （金色 ↔）与修补预览；若在当前锁定格与 K 下 **不存在可行修补**，
   则保留原稿、清空预览并提示“无解”。
4. **预览失效与确认**
   - 预览生成后，只要交织格、锁定格、尺寸或 K 再变动，旧预览立即失效。
   - 只有点击 **“确认：用预览覆盖原稿”** 才会写入原稿（确认时服务端再次
     校验预览与原稿的绑定指纹，过期则拒绝，HTTP 409）。
   - 确认后的编辑与下一次预览都基于最新原稿。

## 本地开发（不用 Docker）

后端（Python 3.11+）：

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export WEAVE_DB_PATH=./weave.db
uvicorn app.main:app --reload --port 8000
```

前端（Node 20+）：

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 ，/api 自动代理到 8000
```

## 项目结构

```
Dockerfile              多阶段构建（Node 构建前端 + Python 运行时）
docker-compose.yml      一键启动、卷持久化、健康检查
backend/
  schema.sql            SQLite 建表脚本（drafts / previews）
  requirements.txt
  app/
    config.py           环境变量配置
    db.py               建库初始化、原稿/预览存取、预览指纹校验
    weave.py            合法性校验与环面连续段分析（超限标注）
    repair.py           MILP 最优修补（最少翻转 + 行展开字典序最小）
    main.py             FastAPI 接口与静态站点托管
frontend/
  src/
    App.jsx             页面、编辑/预览/确认流程
    WeaveGrid.jsx       环面交织格组件
    api.js              接口封装
    styles.css
```

## 求解模型（要点）

- 变量 `y[r,c] ∈ {0,1}` 为修补后格值；锁定格固定为原值。
- 对每个长度 `K+1` 的环面窗口（沿行和沿列），约束
  `1 ≤ Σ窗口 y ≤ 窗口大小−1`，即窗口内必同时含 0 和 1。
  这等价于“不存在长度 > K 的同值连续段”；当窗口退化为整条线时，
  也排除了全同行/列（无限浮长）。
- 第一级最小化翻转格数；第二级把行优先比特流按 20 位分块，
  逐块以二进制数最小化（块序高优先），在翻转数约束下得到唯一的
  行展开字典序最小解。最多 128 个变量，HiGHS 瞬时可解。
