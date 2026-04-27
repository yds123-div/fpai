"""
完全独立的抓取测试脚本（不依赖本项目任何模块）。

用途：
  验证关键数据源是否被拒绝/重定向/notfound/返回 HTML 或返回不完整 JSON。

运行：
  python standalone_fetch_test.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Req:
    name: str
    url: str
    method: str = "GET"
    allow_redirects: bool = True


def snip(s: str, n: int = 240) -> str:
    t = (s or "").replace("\r", "").replace("\n", " ")
    return t[:n] + ("..." if len(t) > n else "")


def looks_html(s: str) -> bool:
    t = (s or "").lstrip().lower()
    return t.startswith("<!doctype html") or t.startswith("<html") or "<head" in t[:400]


def extract_ip_hint(s: str) -> str | None:
    m = re.search(r"Your IP Address:\s*([0-9.]+)", s or "")
    return m.group(1) if m else None


def main() -> int:
    try:
        import requests  # type: ignore
    except Exception as e:
        print("[FATAL] requests not installed:", e)
        return 2

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }

    reqs = [
        Req("Danjuan fund detail", "https://danjuanfunds.com/djapi/fund/detail/000012"),
        Req(
            "Danjuan asset percent",
            "https://danjuanfunds.com/djapi/fundx/base/fund/record/asset/percent?fund_code=000012&report_date=2023-12-31",
        ),
        Req("Eastmoney pingzhongdata (no redirects)", "https://fund.eastmoney.com/pingzhongdata/000012.js", allow_redirects=False),
        Req("Eastmoney pingzhongdata (follow redirects)", "https://fund.eastmoney.com/pingzhongdata/000012.js", allow_redirects=True),
        Req(
            "FundMob manager list (POST)",
            "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNMangerList?FCODE=000012&plat=Android&appType=ttjj&product=EFund&Version=6.2.4&deviceid=diag&MobileKey=diag",
            method="POST",
        ),
    ]

    for r in reqs:
        print("=" * 90)
        print("[TEST]", r.name)
        print("  method=", r.method, "redirects=", r.allow_redirects)
        print("  url=", r.url)
        try:
            resp = requests.request(
                r.method,
                r.url,
                headers=headers,
                timeout=20,
                allow_redirects=r.allow_redirects,
            )
            ct = resp.headers.get("content-type", "")
            try:
                resp.encoding = resp.apparent_encoding
                body = resp.text or ""
            except Exception:
                body = ""

            print("  status=", resp.status_code)
            print("  final_url=", getattr(resp, "url", ""))
            print("  content_type=", ct)
            if resp.status_code in (301, 302, 303, 307, 308):
                print("  redirect_location=", resp.headers.get("location"))
            if resp.status_code == 403:
                ip = extract_ip_hint(body)
                if ip:
                    print("  [HINT] 403 IP=", ip)
            if looks_html(body):
                print("  [HINT] HTML page (notfound/风控/验证码页的可能性很高)")
            print("  body_snip=", snip(body))
        except Exception as e:
            print("  [ERROR] request failed:", e)

    print("=" * 90)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

