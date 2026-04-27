"""
嵌入模型服务 - 使用阿里 DashScope text-embedding-v3
支持单向量检索和查询切分多路检索两种模式
"""
import os
import re
import numpy as np
import faiss
import json
from typing import List, Optional, Dict, Tuple
import dashscope
from dashscope import TextEmbedding

# 配置 DashScope API Key
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

EMBEDDING_DIM = 1024  # text-embedding-v3 维度
FAISS_INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "faiss_index")
ID_MAP_PATH = os.path.join(FAISS_INDEX_PATH, "id_map.json")

# 全局 FAISS index
_faiss_index: Optional[faiss.IndexFlatIP] = None  # 内积 (余弦相似度 on normalized vectors)
_id_map: List[int] = []  # FAISS内部id -> 数据库case id


def inner_product_to_percent(score: float) -> float:
    """
    Convert FAISS inner product score to a percentage similarity score.

    Vectors are L2-normalized before entering FAISS, so inner product is cosine
    similarity in [-1, 1]. The paper-facing score is mapped to [0, 100]:

        percent = ((cosine + 1) / 2) * 100
    """
    clamped = max(-1.0, min(1.0, float(score)))
    return ((clamped + 1.0) / 2.0) * 100.0


def _ensure_dir():
    os.makedirs(FAISS_INDEX_PATH, exist_ok=True)


def get_embedding(text: str) -> np.ndarray:
    """调用阿里 DashScope 获取文本嵌入向量"""
    if not dashscope.api_key:
        # Mock模式：生成确定性伪向量用于开发测试
        return _mock_embedding(text)

    resp = TextEmbedding.call(
        model=TextEmbedding.Models.text_embedding_v3,
        input=text,
        dimension=EMBEDDING_DIM,
    )
    if resp.status_code == 200:
        vec = np.array(resp.output["embeddings"][0]["embedding"], dtype=np.float32)
        # L2 归一化，使内积等价于余弦相似度
        vec = vec / np.linalg.norm(vec)
        return vec
    else:
        raise RuntimeError(f"DashScope Embedding 调用失败: {resp.code} - {resp.message}")


def get_embeddings_batch(texts: List[str]) -> List[np.ndarray]:
    """批量获取嵌入向量"""
    if not dashscope.api_key:
        return [_mock_embedding(t) for t in texts]

    results = []
    # DashScope text-embedding-v3 当前批量限制为 10 条
    for i in range(0, len(texts), 10):
        batch = texts[i:i+10]
        resp = TextEmbedding.call(
            model=TextEmbedding.Models.text_embedding_v3,
            input=batch,
            dimension=EMBEDDING_DIM,
        )
        if resp.status_code == 200:
            for emb in resp.output["embeddings"]:
                vec = np.array(emb["embedding"], dtype=np.float32)
                vec = vec / np.linalg.norm(vec)
                results.append(vec)
        else:
            message = getattr(resp, "message", "")
            print(f"DashScope Embedding 批量调用失败，改为逐条调用: {resp.code} {message}")
            results.extend([get_embedding(text) for text in batch])
    return results


def _mock_embedding(text: str) -> np.ndarray:
    """Mock嵌入：基于文本hash生成伪向量，保证相同文本返回相同向量"""
    import hashlib
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.RandomState(seed)
    vec = rng.randn(EMBEDDING_DIM).astype(np.float32)
    # 加入关键词特征，让相似文本的向量更接近
    keywords_weights = {
        "合同": 0, "纠纷": 1, "违约": 2, "侵权": 3, "赔偿": 4,
        "买卖": 5, "租赁": 6, "劳动": 7, "借款": 8, "担保": 9,
        "离婚": 10, "继承": 11, "房屋": 12, "知识产权": 13, "公司": 14,
        "民事": 15, "刑事": 16, "行政": 17, "原告": 18, "被告": 19,
        "损害": 20, "责任": 21, "协议": 22, "支付": 23, "交付": 24,
    }
    for kw, idx in keywords_weights.items():
        if kw in text:
            vec[idx * 40: (idx + 1) * 40] += 3.0
    vec = vec / np.linalg.norm(vec)
    return vec


def load_faiss_index():
    """加载 FAISS 索引"""
    global _faiss_index, _id_map
    _ensure_dir()
    index_file = os.path.join(FAISS_INDEX_PATH, "index.faiss")
    if os.path.exists(index_file) and os.path.exists(ID_MAP_PATH):
        _faiss_index = faiss.read_index(index_file)
        with open(ID_MAP_PATH, "r") as f:
            _id_map = json.load(f)
    else:
        _faiss_index = faiss.IndexFlatIP(EMBEDDING_DIM)
        _id_map = []


def save_faiss_index():
    """保存 FAISS 索引"""
    _ensure_dir()
    if _faiss_index is not None:
        faiss.write_index(_faiss_index, os.path.join(FAISS_INDEX_PATH, "index.faiss"))
        with open(ID_MAP_PATH, "w") as f:
            json.dump(_id_map, f)


def add_to_index(case_id: int, text: str):
    """将案例文本添加到 FAISS 索引"""
    global _faiss_index, _id_map
    if _faiss_index is None:
        load_faiss_index()
    vec = get_embedding(text)
    _faiss_index.add(vec.reshape(1, -1))
    _id_map.append(case_id)
    save_faiss_index()


def add_batch_to_index(case_ids: List[int], texts: List[str]):
    """批量添加到索引"""
    global _faiss_index, _id_map
    if _faiss_index is None:
        load_faiss_index()
    vecs = get_embeddings_batch(texts)
    vectors = np.stack(vecs)
    _faiss_index.add(vectors)
    _id_map.extend(case_ids)
    save_faiss_index()


def search_similar(text: str, top_k: int = 5) -> List[tuple]:
    """搜索相似案例，返回 [(case_id, similarity_percent), ...]"""
    global _faiss_index, _id_map
    if _faiss_index is None:
        load_faiss_index()
    if _faiss_index.ntotal == 0:
        return []

    vec = get_embedding(text)
    scores, indices = _faiss_index.search(vec.reshape(1, -1), min(top_k, _faiss_index.ntotal))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < len(_id_map) and idx >= 0:
            results.append((_id_map[idx], inner_product_to_percent(float(score))))
    return results


def rebuild_index(cases: list):
    """重建整个 FAISS 索引"""
    global _faiss_index, _id_map
    _faiss_index = faiss.IndexFlatIP(EMBEDDING_DIM)
    _id_map = []

    if not cases:
        save_faiss_index()
        return

    case_ids = []
    texts = []
    for case in cases:
        case_ids.append(case.id)
        texts.append(_build_case_text(case))

    add_batch_to_index(case_ids, texts)


def _build_case_text(case) -> str:
    """将案例对象拼接为用于嵌入的文本"""
    parts = []
    if hasattr(case, 'keywords') and case.keywords:
        parts.append(f"【关键词】{case.keywords}")
    if hasattr(case, 'case_summary') and case.case_summary:
        parts.append(f"【基本案情】{case.case_summary}")
    if hasattr(case, 'dispute_focus') and case.dispute_focus:
        parts.append(f"【争议核心】{case.dispute_focus}")
    if hasattr(case, 'judgment_points') and case.judgment_points:
        parts.append(f"【裁判要点】{case.judgment_points}")
    if hasattr(case, 'related_laws') and case.related_laws:
        parts.append(f"【相关法条】{case.related_laws}")
    if hasattr(case, 'judgment_reason') and case.judgment_reason:
        parts.append(f"【裁判理由】{case.judgment_reason}")
    # 兼容裁判文书CSV数据：如果以上字段都为空，使用全文
    if not parts and hasattr(case, 'full_text') and case.full_text:
        # 全文可能很长，截取前2000字用于嵌入
        parts.append(case.full_text[:2000])
    # 兜底：用案件名称 + 案由
    if not parts:
        fallback = case.case_name or ""
        if hasattr(case, 'cause_of_action') and case.cause_of_action:
            fallback += f" {case.cause_of_action}"
        return fallback
    return "\n".join(parts)


# ============================================================
#  查询切分多路检索（Query Chunking + Multi-route Retrieval）
# ============================================================

def split_query_into_chunks(text: str, min_chunk_len: int = 6) -> List[str]:
    """
    将用户查询文本按句切分为语义单元。
    优先按中文句号/分号/问号/感叹号切分，
    如果切出的句子仍然很长（>80字），再按逗号二次切分。
    短于 min_chunk_len 的片段会被合并到相邻句中。
    """
    if not text or len(text.strip()) < min_chunk_len:
        return [text.strip()] if text and text.strip() else []

    # 第一级：按句号、分号、感叹号、问号、换行切分
    raw_sentences = re.split(r'[。；！？\n]+', text)
    raw_sentences = [s.strip() for s in raw_sentences if s.strip()]

    # 第二级：过长的句子按逗号再切
    sentences = []
    for sent in raw_sentences:
        if len(sent) > 80:
            sub_parts = re.split(r'[，,]+', sent)
            sub_parts = [p.strip() for p in sub_parts if p.strip()]
            # 合并过短的子句
            buffer = ""
            for part in sub_parts:
                if len(buffer) + len(part) < 60:
                    buffer = buffer + "，" + part if buffer else part
                else:
                    if buffer:
                        sentences.append(buffer)
                    buffer = part
            if buffer:
                sentences.append(buffer)
        else:
            sentences.append(sent)

    # 合并过短的片段到前一句
    merged = []
    for sent in sentences:
        if len(sent) < min_chunk_len and merged:
            merged[-1] = merged[-1] + "，" + sent
        else:
            merged.append(sent)

    return merged if merged else [text.strip()]


def search_similar_chunked(text: str, top_k: int = 5) -> List[Tuple[int, float]]:
    """
    查询切分多路检索：
    1. 将查询文本按句切分为多个 chunk
    2. 每个 chunk 独立向量化并检索 Top-K
    3. 合并所有 chunk 的检索结果，按综合得分重新排序

    单路相似度先由 FAISS 内积映射为百分制：
      similarity_percent = ((inner_product + 1) / 2) * 100

    综合得分 = max_score * 0.4 + avg_score * 0.3 + hit_percent * 0.3
      - max_score: 该案例在所有 chunk 中的最高百分制相似度
      - avg_score: 该案例在所有命中 chunk 中的平均百分制相似度
      - hit_percent: 命中该案例的 chunk 数 / 总 chunk 数 * 100
    """
    chunks = split_query_into_chunks(text)

    # 如果只切出 1 个 chunk，退化为普通单向量检索
    if len(chunks) <= 1:
        return search_similar(text, top_k=top_k)

    # 每个 chunk 独立检索，多取一些候选
    per_chunk_k = min(top_k * 3, 20)
    all_hits: Dict[int, List[float]] = {}

    for chunk in chunks:
        results = search_similar(chunk, top_k=per_chunk_k)
        for case_id, score in results:
            if case_id not in all_hits:
                all_hits[case_id] = []
            all_hits[case_id].append(score)

    if not all_hits:
        return []

    # 合并排序
    num_chunks = len(chunks)
    merged = []
    for case_id, scores in all_hits.items():
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)
        hit_percent = len(scores) / num_chunks * 100.0
        combined = max_score * 0.4 + avg_score * 0.3 + hit_percent * 0.3
        merged.append((case_id, round(max(0.0, min(100.0, combined)), 2)))

    merged.sort(key=lambda x: x[1], reverse=True)
    return merged[:top_k]
