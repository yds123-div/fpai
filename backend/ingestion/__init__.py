# 文档接入、解析（MinerU）、分块、向量化任务投递；Worker 消费后写 Milvus（T032）。

from ingestion.submit import submit_document
from ingestion.chunking import chunk_text
from ingestion.queue import push_task, pop_task
from ingestion.processor import process_one_task, run_worker

__all__ = [
    "submit_document",
    "chunk_text",
    "push_task",
    "pop_task",
    "process_one_task",
    "run_worker",
]
