"""
嵌入模型服务 - 使用阿里 DashScope text-embedding-v3
"""
import os
import numpy as np
import faiss
import json
from typing import List, Optional
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
    # DashScope 批量限制25条
    for i in range(0, len(texts), 25):
        batch = texts[i:i+25]
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
            raise RuntimeError(f"DashScope Embedding 批量调用失败: {resp.code}")
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
    """搜索相似案例，返回 [(case_id, score), ...]"""
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
            results.append((_id_map[idx], float(score)))
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
    if case.keywords:
        parts.append(f"【关键词】{case.keywords}")
    if case.case_summary:
        parts.append(f"【基本案情】{case.case_summary}")
    if case.dispute_focus:
        parts.append(f"【争议核心】{case.dispute_focus}")
    if case.judgment_points:
        parts.append(f"【裁判要点】{case.judgment_points}")
    if case.related_laws:
        parts.append(f"【相关法条】{case.related_laws}")
    if case.judgment_reason:
        parts.append(f"【裁判理由】{case.judgment_reason}")
    return "\n".join(parts) if parts else case.case_name
