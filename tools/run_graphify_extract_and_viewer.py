#!/usr/bin/env python3
"""加载项目根 .env，执行 graphify extract，再生成增强版 graph.html。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_OUT = ROOT / "graphify-out"


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def main() -> None:
    extra = load_dotenv(ROOT / ".env")
    env = {**os.environ, **extra}
    graphify = os.environ.get("GRAPHIFY_EXE", "graphify")
    cmd = [
        graphify,
        "extract",
        str(ROOT),
        "--backend",
        "openai",
        "--max-concurrency",
        "2",
    ]
    print("Running:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    if r.returncode != 0:
        sys.exit(r.returncode)
    report = GRAPHIFY_OUT / "GRAPH_REPORT.md"
    if not report.is_file():
        subprocess.run(
            [graphify, "cluster-only", str(ROOT)],
            cwd=ROOT,
            env=env,
            check=False,
        )
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_graphify_enhanced_html.py")],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
