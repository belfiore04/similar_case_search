# Similar Case Search

类案检索系统，包含 FastAPI 后端和 Vite React 前端。

## Mock 状态

当前代码只保留启动时的案例 seed 数据：如果数据库为空，后端会加载 `backend/mock_data/cases.json`。

其他模型能力已经改为真实服务：

- 向量 embedding：必须配置 `DASHSCOPE_API_KEY`
- 查询条件抽取：必须配置 `DEEPSEEK_API_KEY`
- 类案报告生成：必须配置 `DEEPSEEK_API_KEY`

缺少对应 key 时，接口会返回明确的 503 错误，不再静默返回伪结果。

## 本地启动

### 1. 后端

建议使用 Python 3.11 或 3.12。Python 3.14 太新，`pydantic-core`、`faiss-cpu`、`psycopg2-binary` 等原生依赖可能无法安装。

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `backend/.env`，填入真实的 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY` 和 `SECRET_KEY`。

加载环境变量并启动：

```bash
set -a
. .env
set +a
python main.py
```

默认服务地址：

```text
http://localhost:8001
```

首次启动时，如果数据库为空，会自动创建本地账号和 seed 案例：

- `admin / admin123`
- `demo / demo123`

### 2. 重建 FAISS 索引

如果你替换或导入了数据，重新构建向量索引：

```bash
cd backend
set -a
. .env
set +a
python rebuild_faiss_index.py
```

索引文件在 `backend/faiss_index/`。索引会写入 `meta.json`，避免误用旧的非真实 embedding 索引。

### 3. 前端

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

默认前端地址：

```text
http://localhost:5173
```

## 导入真实数据

仓库里保留的 CSV 样本在 `data/` 下。导入 PostgreSQL 的脚本是：

```bash
cd backend
python import_csv_to_pg.py --csv ../data/2021年10月裁判文书数据.csv --db-url postgresql://localhost/similar_case_search
```

导入后设置同一个 `DATABASE_URL`，再运行 `python rebuild_faiss_index.py`。
