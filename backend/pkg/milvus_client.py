"""
Milvus Collection 与封装，见 technical_design §4.3。

Collection 存储 chunk 向量与标量字段：doc_id、source、permission_tag、created_at、chunk_text；
检索按 permission_tag/product_pool 等做过滤（检索前过滤），检索服务封装检索后强过滤与引用输出。
"""
import os
from typing import Any

try:
    from pymilvus import MilvusClient, DataType
except ImportError:
    MilvusClient = None  # type: ignore[misc, assignment]
    DataType = None  # type: ignore[misc, assignment]

_milvus_client: "MilvusClient | None" = None

# Collection 名称与向量维度，从环境读取
COLLECTION_NAME_KEY = "MILVUS_COLLECTION_NAME"
DEFAULT_COLLECTION_NAME = "fpai_chunks"
# FAQ 专用 Collection（向量化 question，检索 TopK 后回表 MySQL 取 answer）
FAQ_COLLECTION_NAME = "fpai_faq"

# 标量字段名（与 technical_design §4.3 一致）
FIELD_ID = "id"
FIELD_VECTOR = "vector"
FIELD_DOC_ID = "doc_id"
FIELD_SOURCE = "source"
FIELD_PERMISSION_TAG = "permission_tag"
FIELD_CREATED_AT = "created_at"
FIELD_CHUNK_TEXT = "chunk_text"

# 标量字段最大长度
VARCHAR_MAX_LEN = 65535


def _uri() -> str:
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    return f"http://{host}:{port}"


def get_collection_name() -> str:
    return os.getenv(COLLECTION_NAME_KEY, DEFAULT_COLLECTION_NAME)


def is_configured() -> bool:
    """是否已配置 Milvus（有 MILVUS_HOST 或默认 localhost）。"""
    return True


def get_client() -> "MilvusClient | None":
    """返回单例 MilvusClient；未安装 pymilvus 或连接失败时返回 None。"""
    global _milvus_client
    if MilvusClient is None:
        return None
    if _milvus_client is not None:
        return _milvus_client
    try:
        _milvus_client = MilvusClient(uri=_uri())
        _milvus_client.list_collections()
    except Exception:
        _milvus_client = None
    return _milvus_client


def close_client() -> None:
    """释放客户端，用于测试或进程退出。"""
    global _milvus_client
    _milvus_client = None


def ensure_collection(
    dimension: int,
    collection_name: str | None = None,
    metric_type: str = "IP",
) -> bool:
    """
    确保 Collection 存在；不存在则创建。
    Schema：id (VARCHAR primary)、vector (FLOAT_VECTOR)、doc_id、source、permission_tag、created_at、chunk_text。
    metric_type：IP（内积）或 COSINE（余弦），与 embedding 归一化一致时用 IP。
    """
    client = get_client()
    if not client or DataType is None:
        return False
    name = collection_name or get_collection_name()
    try:
        existing = client.list_collections()
        if isinstance(existing, list) and name in existing:
            return True
        if isinstance(existing, dict) and name in existing.get("data", []):
            return True
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name=FIELD_ID, datatype=DataType.VARCHAR, max_length=256, is_primary=True)
        schema.add_field(field_name=FIELD_VECTOR, datatype=DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field(field_name=FIELD_DOC_ID, datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name=FIELD_SOURCE, datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name=FIELD_PERMISSION_TAG, datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name=FIELD_CREATED_AT, datatype=DataType.INT64)
        schema.add_field(field_name=FIELD_CHUNK_TEXT, datatype=DataType.VARCHAR, max_length=VARCHAR_MAX_LEN)
        try:
            index_params = client.prepare_index_params()
            index_params.add_index(field_name=FIELD_VECTOR, index_type="IVF_FLAT", metric_type=metric_type, params={"nlist": 128})
            client.create_collection(collection_name=name, schema=schema, index_params=index_params)
        except TypeError:
            client.create_collection(collection_name=name, schema=schema, dimension=dimension)
    except Exception:
        return False
    return True


def insert_chunks(
    ids: list[str],
    vectors: list[list[float]],
    doc_ids: list[str],
    sources: list[str],
    permission_tags: list[str],
    created_ats: list[int],
    chunk_texts: list[str],
    collection_name: str | None = None,
) -> bool:
    """插入一批 chunk；列表长度应一致。"""
    client = get_client()
    if not client:
        return False
    name = collection_name or get_collection_name()
    if not (len(ids) == len(vectors) == len(doc_ids) == len(sources) == len(permission_tags) == len(created_ats) == len(chunk_texts)):
        return False
    try:
        data = [
            {FIELD_ID: i, FIELD_VECTOR: v, FIELD_DOC_ID: d, FIELD_SOURCE: s, FIELD_PERMISSION_TAG: p, FIELD_CREATED_AT: c, FIELD_CHUNK_TEXT: t}
            for i, v, d, s, p, c, t in zip(ids, vectors, doc_ids, sources, permission_tags, created_ats, chunk_texts)
        ]
        client.insert(collection_name=name, data=data)
    except Exception:
        return False
    return True


def search_with_filter(
    query_vectors: list[list[float]],
    filter_expr: str | None = None,
    top_k: int = 10,
    output_fields: list[str] | None = None,
    collection_name: str | None = None,
) -> list[list[dict[str, Any]]]:
    """
    向量检索，支持按标量过滤（如 permission_tag）。
    filter_expr 示例：'permission_tag in ["pool1", "pool2"]' 或 'doc_id == "xxx"'。
    返回 shape [len(query_vectors)][top_k]，每个元素为 hit 的 dict（含 id、distance、output_fields）。
    """
    client = get_client()
    if not client:
        return []
    name = collection_name or get_collection_name()
    out_fields = output_fields or [FIELD_DOC_ID, FIELD_SOURCE, FIELD_CHUNK_TEXT, FIELD_PERMISSION_TAG]
    try:
        results = client.search(
            collection_name=name,
            data=query_vectors,
            filter=filter_expr,
            limit=top_k,
            output_fields=out_fields,
        )
        return results
    except Exception:
        return []


def delete_by_filter(
    collection_name: str,
    filter_expr: str,
) -> bool:
    """
    按标量条件删除实体；用于 FAQ 全量同步前清空 source=faq。
    filter_expr 示例：'source == "faq"'。不可与 ids 同用。
    """
    client = get_client()
    if not client or not filter_expr:
        return False
    try:
        client.delete(collection_name=collection_name, filter=filter_expr)
        return True
    except Exception:
        return False
