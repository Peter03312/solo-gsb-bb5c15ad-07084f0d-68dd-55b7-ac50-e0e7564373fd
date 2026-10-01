# 多阶段构建：Node 构建 React 静态文件，Python 运行 API 并直接托管静态文件
FROM node:20-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WEAVE_DB_PATH=/data/weave.db \
    WEAVE_FRONTEND_DIST=/app/frontend/dist
WORKDIR /app

# scipy/numpy 走 wheel 安装，无需编译工具链
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /build/dist ./frontend/dist

# /data 存放 SQLite 数据库，可由卷持久化
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/state').status==200 else 1)"

# 启动时自动执行建表与初始化（db.init_db 幂等）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
