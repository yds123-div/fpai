from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path


DEFAULT_TEXT = Path(r"D:\neatdowlode\Compressed\txt\02_noisy_board_resolution.txt")
DEFAULT_ISSUE_CSV = Path(r"D:\neatdowlode\Compressed\issue_catalog.csv")


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _build_pycorrector():
    import pycorrector  # type: ignore

    if hasattr(pycorrector, "correct") and callable(pycorrector.correct):
        def _predict(text: str) -> str:
            corrected, _ = pycorrector.correct(text)
            return corrected

        return _predict, "pycorrector.correct"

    from pycorrector import ProperCorrector  # type: ignore

    proper = ProperCorrector()

    def _predict(text: str) -> str:
        res = proper.correct(text)
        if isinstance(res, dict):
            tgt = res.get("target")
            if isinstance(tgt, str):
                return tgt
        return str(res)

    return _predict, "ProperCorrector.correct"


def _char_level_changes(src: str, pred: str) -> list[dict]:
    n = max(len(src), len(pred))
    src_pad = src.ljust(n)
    pred_pad = pred.ljust(n)
    changes: list[dict] = []
    for i, (a, b) in enumerate(zip(src_pad, pred_pad)):
        if a != b:
            changes.append({"pos": i, "from": a, "to": b})
    return changes


def _infer_file_id(text_file: Path) -> str:
    name = text_file.name
    if len(name) >= 2 and name[:2].isdigit():
        return f"D{name[:2]}"
    return "D02"


def _load_expected_issues(issue_csv: Path, file_id: str) -> list[dict]:
    if not issue_csv.exists():
        return []
    rows: list[dict] = []
    with issue_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("file_id", "").strip() != file_id:
                continue
            issue_type = row.get("issue_type", "").strip()
            observed = row.get("observed_or_missing", "").strip()
            expected = row.get("expected_or_fix", "").strip()
            if issue_type == "错别字" and observed and expected:
                rows.append(
                    {
                        "issue_type": issue_type,
                        "observed": observed,
                        "expected": expected,
                        "location": row.get("location", "").strip(),
                    }
                )
    return rows


def _evaluate_expected(pred: str, expected_issues: list[dict]) -> list[dict]:
    results: list[dict] = []
    for item in expected_issues:
        observed = item["observed"]
        expected = item["expected"]
        fixed = (expected in pred) and (observed not in pred)
        out = dict(item)
        out["fixed"] = fixed
        results.append(out)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Show pycorrector result for one file")
    parser.add_argument("--text-file", default=str(DEFAULT_TEXT), help="Input txt file path")
    parser.add_argument("--issue-csv", default=str(DEFAULT_ISSUE_CSV), help="issue_catalog.csv path")
    parser.add_argument("--file-id", default="", help="Dataset file id, e.g. D02/D04; auto infer if empty")
    parser.add_argument(
        "--output",
        default="tests/pycorrector_single_file_result.json",
        help="Result JSON path",
    )
    args = parser.parse_args()

    text_file = Path(args.text_file)
    issue_csv = Path(args.issue_csv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    source = _load_text(text_file)
    file_id = args.file_id.strip() or _infer_file_id(text_file)
    t0 = time.perf_counter()
    predict, api_name = _build_pycorrector()
    t1 = time.perf_counter()
    corrected = predict(source)
    t2 = time.perf_counter()

    changes = _char_level_changes(source, corrected)
    expected_issues = _load_expected_issues(issue_csv, file_id)
    issue_eval = _evaluate_expected(corrected, expected_issues)
    hit = sum(1 for x in issue_eval if x["fixed"])

    result = {
        "text_file": str(text_file),
        "file_id": file_id,
        "pycorrector_api": api_name,
        "build_ms": (t1 - t0) * 1000,
        "predict_ms": (t2 - t1) * 1000,
        "total_ms": (t2 - t0) * 1000,
        "source_length": len(source),
        "corrected_length": len(corrected),
        "changed_char_count": len(changes),
        "changes_preview": changes[:200],
        "expected_typo_issue_count": len(issue_eval),
        "expected_typo_fixed_count": hit,
        "expected_typo_fixed_rate": (hit / len(issue_eval)) if issue_eval else 0.0,
        "issue_eval": issue_eval,
        "source_preview": source[:1200],
        "corrected_preview": corrected[:1200],
    }

    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] output={output}")
    print(
        "[RESULT]",
        json.dumps(
            {
                "changed_char_count": result["changed_char_count"],
                "expected_typo_issue_count": result["expected_typo_issue_count"],
                "expected_typo_fixed_count": result["expected_typo_fixed_count"],
                "expected_typo_fixed_rate": result["expected_typo_fixed_rate"],
            },
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    main()
