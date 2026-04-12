"""
检索效果对比实验脚本
用途：对比 语义检索（查询切分多路） vs TF-IDF关键词检索 的效果差异
输出：P@5 和 MRR 指标对比表，可直接用于论文 6.3 节

使用方法：
  export DATABASE_URL="postgresql://localhost/similar_case_search"
  export DASHSCOPE_API_KEY="你的Key"
  python run_experiment.py
"""

import os
import sys
import json
import time
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from models import LegalCase
from services.embedding import (
    search_similar,
    search_similar_chunked,
    load_faiss_index,
    _faiss_index,
)

# ============================================================
#  TF-IDF 基线检索
# ============================================================

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TfidfBaseline:
    """TF-IDF 关键词检索基线"""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=10000,
            token_pattern=r"(?u)\b\w+\b",  # 支持中文单字
        )
        self.case_ids = []
        self.tfidf_matrix = None

    def build_index(self, case_ids, texts):
        self.case_ids = case_ids
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)
        print(f"[TF-IDF] 索引构建完成，{len(case_ids)} 条文档，{self.tfidf_matrix.shape[1]} 个特征词")

    def search(self, query, top_k=5):
        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self.case_ids[i], float(scores[i])) for i in top_indices]


# ============================================================
#  测试查询（覆盖民事、刑事、行政三类）
# ============================================================

TEST_QUERIES = [
    {
        "name": "买卖合同货款纠纷",
        "type": "民事",
        "description": "原告与被告签订货物买卖合同，约定被告购买一批电子产品，总价款50万元。原告按约交付全部货物后，被告仅支付部分货款，剩余款项经多次催要仍未支付，原告要求被告支付剩余货款及违约金。",
        "relevant_causes": ["买卖合同纠纷", "合同纠纷"],
    },
    {
        "name": "劳动合同违法解除",
        "type": "民事",
        "description": "原告在被告公司工作多年，公司以经营困难为由单方面解除劳动合同，未按法定程序提前通知，也未足额支付经济补偿金。原告认为公司构成违法解除，要求支付赔偿金。",
        "relevant_causes": ["劳动合同纠纷", "劳动争议"],
    },
    {
        "name": "民间借贷还款纠纷",
        "type": "民事",
        "description": "原告与被告系朋友关系，被告因资金周转向原告借款，双方签订借款协议并约定利率和还款期限。借款到期后被告未按约还款，原告要求归还本金及利息。",
        "relevant_causes": ["民间借贷纠纷", "借款合同纠纷"],
    },
    {
        "name": "机动车交通事故赔偿",
        "type": "民事",
        "description": "被告驾驶机动车与原告发生交通事故，造成原告人身损害，经交警认定被告负主要责任。原告要求被告及保险公司赔偿医疗费、误工费、伤残赔偿金等各项损失。",
        "relevant_causes": ["机动车交通事故责任纠纷", "交通事故"],
    },
    {
        "name": "房屋租赁合同纠纷",
        "type": "民事",
        "description": "原告将房屋出租给被告使用，被告连续多月拖欠租金拒不支付，原告要求解除租赁合同并要求被告腾退房屋、支付拖欠的租金。",
        "relevant_causes": ["租赁合同纠纷", "房屋租赁合同纠纷"],
    },
    {
        "name": "离婚财产分割纠纷",
        "type": "民事",
        "description": "原告与被告协议离婚后，就婚后共同财产的分割产生争议，被告拒绝按离婚协议约定配合办理房产过户手续，原告诉请法院判令被告履行协议。",
        "relevant_causes": ["离婚后财产纠纷", "离婚纠纷"],
    },
    {
        "name": "危险驾驶醉酒驾车",
        "type": "刑事",
        "description": "被告人酒后驾驶机动车在道路上行驶被交警查获，经鉴定血液中酒精含量远超法定标准，属于醉酒驾驶机动车，公诉机关以危险驾驶罪提起公诉。",
        "relevant_causes": ["危险驾驶罪", "危险驾驶"],
    },
    {
        "name": "盗窃犯罪案件",
        "type": "刑事",
        "description": "被告人多次秘密窃取他人财物，涉案金额较大，被公安机关抓获后如实供述犯罪事实，公诉机关以盗窃罪提起公诉，建议判处有期徒刑并处罚金。",
        "relevant_causes": ["盗窃罪", "盗窃"],
    },
    {
        "name": "环保行政处罚争议",
        "type": "行政",
        "description": "某企业因违规排放废气废水被生态环境部门立案调查并作出行政处罚决定，企业认为处罚认定事实不清、程序违法，向法院提起行政诉讼。",
        "relevant_causes": ["行政处罚", "环境保护"],
    },
    {
        "name": "工商行政登记纠纷",
        "type": "行政",
        "description": "原告认为市场监督管理部门作出的工商变更登记行为违法，侵犯了其合法权益，请求法院依法撤销该行政行为并恢复原登记状态。",
        "relevant_causes": ["行政登记", "工商登记", "行政撤销"],
    },
]


# ============================================================
#  相关性判定
# ============================================================

def is_relevant(case, query):
    """
    判定检索到的案例是否与查询相关。
    策略：
    1. 案由匹配（模糊匹配 relevant_causes 中的任何一个关键词）
    2. 案件类型匹配
    3. 案件名称中包含查询相关的关键词
    """
    score = 0

    cause = (case.cause_of_action or "").strip()
    case_name = (case.case_name or "").strip()
    case_type = (case.case_type or "").strip()
    full_text = (case.full_text or "")

    # 案由匹配（最重要）
    for rc in query["relevant_causes"]:
        if rc in cause or cause in rc:
            score += 3
            break
        # 部分匹配
        rc_chars = set(rc)
        cause_chars = set(cause)
        if len(rc_chars & cause_chars) >= min(len(rc_chars), 2):
            score += 1

    # 案件类型匹配
    query_type = query["type"]
    if query_type in case_type:
        score += 1

    # 案件名称关键词匹配
    desc_keywords = set(query["description"][::3])  # 采样一些字
    name_overlap = sum(1 for c in query["relevant_causes"] if any(kw in case_name for kw in c))
    if name_overlap > 0:
        score += 1

    return score >= 2


# ============================================================
#  评估指标计算
# ============================================================

def calc_precision_at_k(relevances, k):
    """P@K: 前K条中相关案例的比例"""
    top_k = relevances[:k]
    if not top_k:
        return 0.0
    return sum(top_k) / len(top_k)


def calc_mrr(relevances):
    """MRR: 第一条相关结果的倒数排名"""
    for i, rel in enumerate(relevances):
        if rel:
            return 1.0 / (i + 1)
    return 0.0


# ============================================================
#  主实验流程
# ============================================================

def run_experiment():
    print("=" * 60)
    print("  类案检索效果对比实验")
    print("  语义检索（查询切分多路） vs TF-IDF 关键词检索")
    print("=" * 60)

    # 1. 加载数据
    db = SessionLocal()
    cases = db.query(LegalCase).all()
    print(f"\n[数据] 案例总数: {len(cases)}")

    case_map = {c.id: c for c in cases}

    # 2. 构建 TF-IDF 索引
    print("[TF-IDF] 构建索引...")
    tfidf = TfidfBaseline()
    tfidf_ids = []
    tfidf_texts = []
    for c in cases:
        tfidf_ids.append(c.id)
        # 用和语义检索相同的文本拼接方式
        text_parts = []
        if c.case_name:
            text_parts.append(c.case_name)
        if c.cause_of_action:
            text_parts.append(c.cause_of_action)
        if c.case_summary:
            text_parts.append(c.case_summary)
        if c.full_text:
            text_parts.append(c.full_text[:2000])
        if c.keywords:
            text_parts.append(c.keywords)
        tfidf_texts.append(" ".join(text_parts) if text_parts else c.case_name or "")
    tfidf.build_index(tfidf_ids, tfidf_texts)

    # 3. 加载 FAISS 索引
    print("[FAISS] 加载向量索引...")
    load_faiss_index()
    from services.embedding import _faiss_index as fi
    if fi is None or fi.ntotal == 0:
        print("[错误] FAISS 索引为空！请先启动 main.py 构建索引。")
        print("  运行: export DASHSCOPE_API_KEY=你的Key && python main.py")
        sys.exit(1)
    print(f"[FAISS] 索引中共 {fi.ntotal} 个向量")

    # 4. 逐条查询，收集结果
    TOP_K = 5
    results_semantic = []  # [(query_name, query_type, p5, mrr)]
    results_tfidf = []

    print(f"\n{'─' * 60}")
    print(f"  开始实验（{len(TEST_QUERIES)} 条测试查询，Top-{TOP_K}）")
    print(f"{'─' * 60}")

    for i, query in enumerate(TEST_QUERIES):
        query_text = f"【案件名称】{query['name']}\n【案情描述】{query['description']}"
        print(f"\n[{i+1}/{len(TEST_QUERIES)}] {query['name']}（{query['type']}）")

        # --- 语义检索（切分多路）---
        sem_results = search_similar_chunked(query_text, top_k=TOP_K)
        sem_relevances = []
        for case_id, score in sem_results:
            case = case_map.get(case_id)
            if case:
                rel = is_relevant(case, query)
                sem_relevances.append(1 if rel else 0)
                cause = (case.cause_of_action or "未知")[:15]
                print(f"    语义 #{len(sem_relevances)}: {cause:16s} | 分数={score:.4f} | {'✓相关' if rel else '✗不相关'}")
            else:
                sem_relevances.append(0)

        sem_p5 = calc_precision_at_k(sem_relevances, TOP_K)
        sem_mrr = calc_mrr(sem_relevances)
        results_semantic.append((query["name"], query["type"], sem_p5, sem_mrr))

        # --- TF-IDF 关键词检索 ---
        tfidf_results = tfidf.search(query["description"], top_k=TOP_K)
        tfidf_relevances = []
        for case_id, score in tfidf_results:
            case = case_map.get(case_id)
            if case:
                rel = is_relevant(case, query)
                tfidf_relevances.append(1 if rel else 0)
                cause = (case.cause_of_action or "未知")[:15]
                print(f"    TF-IDF #{len(tfidf_relevances)}: {cause:16s} | 分数={score:.4f} | {'✓相关' if rel else '✗不相关'}")
            else:
                tfidf_relevances.append(0)

        tfidf_p5 = calc_precision_at_k(tfidf_relevances, TOP_K)
        tfidf_mrr = calc_mrr(tfidf_relevances)
        results_tfidf.append((query["name"], query["type"], tfidf_p5, tfidf_mrr))

    db.close()

    # 5. 输出汇总表格
    print(f"\n\n{'═' * 80}")
    print(f"  实验结果汇总")
    print(f"{'═' * 80}")
    print(f"\n{'测试案例':<20s} {'类型':<6s} │ {'语义P@5':>8s} {'语义MRR':>8s} │ {'TF-IDF P@5':>10s} {'TF-IDF MRR':>10s}")
    print(f"{'─' * 20} {'─' * 6} ┼ {'─' * 8} {'─' * 8} ┼ {'─' * 10} {'─' * 10}")

    for i in range(len(TEST_QUERIES)):
        sn, st, sp, sm = results_semantic[i]
        _, _, tp, tm = results_tfidf[i]
        print(f"{sn:<20s} {st:<6s} │ {sp:>8.2f} {sm:>8.2f} │ {tp:>10.2f} {tm:>10.2f}")

    # 计算平均值
    avg_sem_p5 = np.mean([r[2] for r in results_semantic])
    avg_sem_mrr = np.mean([r[3] for r in results_semantic])
    avg_tfidf_p5 = np.mean([r[2] for r in results_tfidf])
    avg_tfidf_mrr = np.mean([r[3] for r in results_tfidf])

    print(f"{'─' * 20} {'─' * 6} ┼ {'─' * 8} {'─' * 8} ┼ {'─' * 10} {'─' * 10}")
    print(f"{'平均值':<20s} {'':6s} │ {avg_sem_p5:>8.2f} {avg_sem_mrr:>8.2f} │ {avg_tfidf_p5:>10.2f} {avg_tfidf_mrr:>10.2f}")

    # 提升幅度
    p5_lift = ((avg_sem_p5 - avg_tfidf_p5) / avg_tfidf_p5 * 100) if avg_tfidf_p5 > 0 else float('inf')
    mrr_lift = ((avg_sem_mrr - avg_tfidf_mrr) / avg_tfidf_mrr * 100) if avg_tfidf_mrr > 0 else float('inf')

    print(f"\n{'═' * 80}")
    print(f"  结论")
    print(f"{'═' * 80}")
    print(f"  语义检索 P@5 平均值:   {avg_sem_p5:.4f}")
    print(f"  TF-IDF  P@5 平均值:    {avg_tfidf_p5:.4f}")
    print(f"  P@5 提升幅度:          {p5_lift:+.1f}%")
    print(f"")
    print(f"  语义检索 MRR 平均值:   {avg_sem_mrr:.4f}")
    print(f"  TF-IDF  MRR 平均值:    {avg_tfidf_mrr:.4f}")
    print(f"  MRR 提升幅度:          {mrr_lift:+.1f}%")
    print(f"{'═' * 80}")


if __name__ == "__main__":
    run_experiment()
