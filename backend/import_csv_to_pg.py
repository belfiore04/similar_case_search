"""
本地数据导入脚本 —— 在你的 Mac 上运行
功能：
  1. 读取裁判文书 CSV 文件
  2. 过滤掉执行案件，只保留民事/刑事/行政案件
  3. 统计各类型数据量
  4. 导入 PostgreSQL 数据库

使用方法：
  # 第一步：安装 PostgreSQL（如果没装过）
  brew install postgresql@15
  brew services start postgresql@15

  # 第二步：创建数据库
  createdb similar_case_search

  # 第三步：安装 Python 依赖
  pip install sqlalchemy psycopg2-binary

  # 第四步：运行本脚本
  python import_csv_to_pg.py --csv /path/to/your/data.csv

  # 可选参数：
  #   --csv          CSV 文件路径（必填）
  #   --db-url       数据库连接串（默认: postgresql://localhost/similar_case_search）
  #   --limit        导入条数上限（用于测试，默认不限制）
  #   --encoding     CSV 编码（默认 utf-8，Windows 导出的可能是 gbk）
  #   --stats-only   只统计不导入
"""

import csv
import argparse
import sys
import time
from collections import Counter

# ---- 数据库部分（仅在非 stats-only 模式下使用）----

def get_engine(db_url):
    from sqlalchemy import create_engine
    return create_engine(db_url, pool_size=5, echo=False)


def create_tables(engine):
    from sqlalchemy import Column, Integer, String, Text, DateTime, MetaData, Table
    from sqlalchemy.sql import func

    metadata = MetaData()
    Table(
        "legal_cases", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("case_name", String(200), nullable=False),
        Column("case_number", String(100), index=True),
        Column("case_type", String(50), index=True),
        Column("cause_of_action", String(200)),
        Column("court", String(100)),
        Column("region", String(100)),
        Column("procedure", String(50)),
        Column("judge_date", String(50)),
        Column("publish_date", String(50)),
        Column("parties", Text),
        Column("plaintiff", String(200)),
        Column("defendant", String(200)),
        Column("case_summary", Text),
        Column("dispute_focus", Text),
        Column("judgment_result", Text),
        Column("judgment_reason", Text),
        Column("judgment_points", Text),
        Column("related_laws", Text),
        Column("keywords", String(500)),
        Column("full_text", Text),
        Column("source_url", String(500)),
        Column("created_at", DateTime, server_default=func.now()),
    )
    metadata.create_all(engine)
    print("[OK] 数据表已创建/确认存在")


def parse_parties(parties_str):
    """从当事人字符串中尝试解析原告和被告（简单启发式）"""
    if not parties_str:
        return "", ""
    parts = [p.strip() for p in parties_str.replace("；", ";").split(";") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], ""
    return "", ""


# CSV 列名 -> 数据库字段名 映射
CSV_COLUMN_MAP = {
    "原始链接": "source_url",
    "案号": "case_number",
    "案件名称": "case_name",
    "法院": "court",
    "所属地区": "region",
    "案件类型": "case_type",
    "审理程序": "procedure",
    "裁判日期": "judge_date",
    "公开日期": "publish_date",
    "当事人": "parties",
    "案由": "cause_of_action",
    "法律依据": "related_laws",
    "全文": "full_text",
}

# 要保留的案件类型（排除"执行案件"）
KEEP_CASE_TYPES = {"民事案件", "刑事案件", "行政案件"}

# 也兼容没有"案件"后缀的写法
KEEP_CASE_TYPES_LOOSE = {"民事", "刑事", "行政", "民事案件", "刑事案件", "行政案件"}


def should_keep(case_type_str):
    """判断是否保留该案件"""
    if not case_type_str:
        return False
    ct = case_type_str.strip()
    return ct in KEEP_CASE_TYPES_LOOSE


def process_csv(csv_path, encoding, limit, stats_only, db_url):
    """主处理流程"""
    print(f"\n[读取] {csv_path} (编码: {encoding})")

    type_counter = Counter()
    kept_counter = Counter()
    total_rows = 0
    kept_rows = 0
    has_fulltext_count = 0
    batch = []
    batch_size = 500
    engine = None

    if not stats_only:
        engine = get_engine(db_url)
        create_tables(engine)

    with open(csv_path, "r", encoding=encoding, errors="replace") as f:
        reader = csv.DictReader(f)

        # 验证列名
        if reader.fieldnames:
            print(f"[列名] {', '.join(reader.fieldnames)}")
            missing = [k for k in CSV_COLUMN_MAP.keys() if k not in reader.fieldnames]
            if missing:
                print(f"[警告] CSV 中缺少以下列: {missing}")

        for row in reader:
            total_rows += 1
            case_type = row.get("案件类型", "").strip()
            type_counter[case_type] += 1

            if not should_keep(case_type):
                continue

            kept_rows += 1
            kept_counter[case_type] += 1
            full_text = row.get("全文", "").strip()
            if len(full_text) > 50:
                has_fulltext_count += 1

            if limit and kept_rows > limit:
                break

            if not stats_only:
                # 构建数据库记录
                parties = row.get("当事人", "")
                plaintiff, defendant = parse_parties(parties)
                record = {}
                for csv_col, db_col in CSV_COLUMN_MAP.items():
                    record[db_col] = row.get(csv_col, "").strip() or None
                record["plaintiff"] = plaintiff or None
                record["defendant"] = defendant or None
                batch.append(record)

                if len(batch) >= batch_size:
                    _insert_batch(engine, batch)
                    batch = []
                    print(f"  已导入 {kept_rows} 条...", end="\r")

            if total_rows % 100000 == 0:
                print(f"  已扫描 {total_rows} 行, 保留 {kept_rows} 条...")

    # 插入剩余
    if batch and not stats_only:
        _insert_batch(engine, batch)

    # 打印统计
    print(f"\n{'='*50}")
    print(f"统计结果")
    print(f"{'='*50}")
    print(f"CSV 总行数:        {total_rows}")
    print(f"保留条数(非执行):   {kept_rows}")
    print(f"有全文内容的:       {has_fulltext_count}")
    print(f"全文覆盖率:         {has_fulltext_count/kept_rows*100:.1f}%" if kept_rows > 0 else "")
    print(f"\n各案件类型分布（原始）:")
    for ct, count in type_counter.most_common():
        marker = " ✓ 保留" if should_keep(ct) else " ✗ 过滤"
        print(f"  {ct or '(空)':12s}: {count:>8,} 条{marker}")
    print(f"\n保留的案件类型分布:")
    for ct, count in kept_counter.most_common():
        print(f"  {ct:12s}: {count:>8,} 条")

    if not stats_only:
        print(f"\n[完成] 已导入 {kept_rows} 条到 PostgreSQL")
    else:
        print(f"\n[仅统计模式] 未导入数据库。去掉 --stats-only 参数可执行导入。")


def _insert_batch(engine, batch):
    """批量插入"""
    from sqlalchemy import text
    columns = list(batch[0].keys())
    placeholders = ", ".join([f":{col}" for col in columns])
    col_names = ", ".join(columns)
    sql = text(f"INSERT INTO legal_cases ({col_names}) VALUES ({placeholders})")
    with engine.begin() as conn:
        conn.execute(sql, batch)


def main():
    parser = argparse.ArgumentParser(description="裁判文书 CSV 导入 PostgreSQL")
    parser.add_argument("--csv", required=True, help="CSV 文件路径")
    parser.add_argument("--db-url", default="postgresql://localhost/similar_case_search",
                        help="PostgreSQL 连接串")
    parser.add_argument("--limit", type=int, default=0, help="导入条数上限（0=不限）")
    parser.add_argument("--encoding", default="utf-8", help="CSV 编码（utf-8 或 gbk）")
    parser.add_argument("--stats-only", action="store_true", help="只统计不导入")
    args = parser.parse_args()

    start = time.time()
    process_csv(args.csv, args.encoding, args.limit, args.stats_only, args.db_url)
    elapsed = time.time() - start
    print(f"\n耗时: {elapsed:.1f} 秒")


if __name__ == "__main__":
    main()
