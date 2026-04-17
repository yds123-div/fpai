from __future__ import annotations

from datetime import date, timedelta
import sys
from pathlib import Path

# 让测试在仓库根目录运行时也能 import backend 包内模块（pkg/*）
_backend_dir = (Path(__file__).resolve().parent.parent / "backend").as_posix()
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from pkg.akshare_client import AkShareClient


def _mk_records(days: int) -> list[dict]:
    """
    构造从 (today-days) 到 today 的逐日记录（含净值日期字段）。
    注意：这里只测试“按日期窗口裁剪”逻辑，不依赖外网 AkShare。
    """
    end = date(2026, 4, 16)
    out: list[dict] = []
    for i in range(days + 1):
        d = end - timedelta(days=(days - i))
        out.append({"净值日期": d.isoformat(), "单位净值": 1.0})
    return out


def test_filter_nav_records_by_period_monotonic() -> None:
    records = _mk_records(2000)  # 足够覆盖 3年窗口

    p1m = AkShareClient._filter_nav_records_by_period(records, "1月")
    p3m = AkShareClient._filter_nav_records_by_period(records, "3月")
    p1y = AkShareClient._filter_nav_records_by_period(records, "1年")
    p3y = AkShareClient._filter_nav_records_by_period(records, "3年")
    psince = AkShareClient._filter_nav_records_by_period(records, "成立来")

    assert len(p1m) <= len(p3m) <= len(p1y) <= len(p3y) <= len(psince)
    assert len(psince) == len(records)


def test_filter_nav_records_by_period_keeps_end_date() -> None:
    records = _mk_records(500)
    end = records[-1]["净值日期"]
    out = AkShareClient._filter_nav_records_by_period(records, "1月")
    assert out[-1]["净值日期"] == end

