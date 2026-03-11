"""
MinIO 客户端与 Bucket 约定，见 technical_design §4.4。

Bucket：原始文档与解析中间产物（fpai-docs）、审计冷数据归档（fpai-audit）；
路径规范：tenant/type/year-month/doc_id，便于保留周期与导出。
"""
import os
from typing import Any, BinaryIO

try:
    from minio import Minio
except ImportError:
    Minio = None  # type: ignore[misc, assignment]

_minio_client: "Minio | None" = None

# Bucket 名称，从环境读取，与 .env.example 一致
BUCKET_DOCS_KEY = "MINIO_BUCKET_DOCS"
BUCKET_AUDIT_KEY = "MINIO_BUCKET_AUDIT"
DEFAULT_BUCKET_DOCS = "fpai-docs"
DEFAULT_BUCKET_AUDIT = "fpai-audit"


def get_bucket_docs() -> str:
    """原始文档、解析后文本/分块结果所在 Bucket。"""
    return os.getenv(BUCKET_DOCS_KEY, DEFAULT_BUCKET_DOCS)


def get_bucket_audit() -> str:
    """审计冷数据归档所在 Bucket。"""
    return os.getenv(BUCKET_AUDIT_KEY, DEFAULT_BUCKET_AUDIT)


def build_object_name(
    tenant: str,
    type_: str,
    year_month: str,
    doc_id: str,
) -> str:
    """
    按 technical_design §4.4 路径规范生成对象名：tenant/type/year-month/doc_id。
    便于按租户、类型、时间与 doc_id 管理保留周期与导出。
    """
    return f"{tenant.strip()}/{type_.strip()}/{year_month.strip()}/{doc_id.strip()}"


def _client_params() -> dict[str, Any]:
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000").strip()
    if "://" in endpoint:
        # 含协议时去掉，Minio 用 separate secure 参数
        endpoint = endpoint.split("://", 1)[1]
    secure = os.getenv("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
    return {
        "endpoint": endpoint,
        "access_key": os.getenv("MINIO_ACCESS_KEY", "").strip(),
        "secret_key": os.getenv("MINIO_SECRET_KEY", "").strip(),
        "secure": secure,
    }


def is_configured() -> bool:
    """是否已配置 MinIO（至少填写了 access_key）。"""
    return bool(_client_params()["access_key"])


def get_client() -> "Minio | None":
    """
    返回单例 MinIO 客户端；未安装 minio 或未配置 MINIO_ACCESS_KEY 时返回 None。
    """
    global _minio_client
    if Minio is None:
        return None
    params = _client_params()
    if not params["access_key"]:
        return None
    if _minio_client is not None:
        return _minio_client
    try:
        _minio_client = Minio(
            params["endpoint"],
            access_key=params["access_key"],
            secret_key=params["secret_key"],
            secure=params["secure"],
        )
        # 探测连通性（列出 bucket 不创建）
        _minio_client.list_buckets()
    except Exception:
        _minio_client = None
    return _minio_client


def close_client() -> None:
    """释放 MinIO 客户端，用于测试或进程退出。"""
    global _minio_client
    _minio_client = None


def ensure_bucket(bucket: str) -> bool:
    """确保 Bucket 存在，不存在则创建。"""
    client = get_client()
    if not client:
        return False
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except Exception:
        return False
    return True


def put_object(
    bucket: str,
    object_name: str,
    data: BinaryIO | bytes,
    length: int | None = None,
    content_type: str = "application/octet-stream",
) -> bool:
    """上传对象；data 为 bytes 时自动计算 length。"""
    client = get_client()
    if not client:
        return False
    if isinstance(data, bytes):
        import io
        data = io.BytesIO(data)
        length = length if length is not None else len(data.getvalue())
        data.seek(0)
    if length is None:
        length = -1
    try:
        client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=data,
            length=length,
            content_type=content_type,
        )
    except Exception:
        return False
    return True


def get_object(bucket: str, object_name: str) -> bytes | None:
    """下载对象，返回完整内容；不存在或失败返回 None。调用方无需 close response。"""
    client = get_client()
    if not client:
        return None
    try:
        response = client.get_object(bucket_name=bucket, object_name=object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except Exception:
        return None


def remove_object(bucket: str, object_name: str) -> bool:
    """删除对象。"""
    client = get_client()
    if not client:
        return False
    try:
        client.remove_object(bucket_name=bucket, object_name=object_name)
    except Exception:
        return False
    return True


def stat_object(bucket: str, object_name: str) -> dict[str, Any] | None:
    """获取对象元数据；不存在返回 None。"""
    client = get_client()
    if not client:
        return None
    try:
        st = client.stat_object(bucket_name=bucket, object_name=object_name)
        return {
            "size": st.size,
            "etag": getattr(st, "etag", None),
            "content_type": getattr(st, "content_type", None),
            "last_modified": getattr(st, "last_modified", None),
        }
    except Exception:
        return None
