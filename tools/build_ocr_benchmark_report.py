import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd


DEFAULT_KEY = "사건번호"
DEFAULT_FIELDS = [
    "사건번호",
    "법원명",
    "물건번호",
    "주소",
    "아파트명",
    "감정가",
    "최저매각가격",
    "부채총액",
    "KB시세",
    "주요채권자",
    "근저당여부",
    "압류여부",
    "가압류여부",
    "가처분여부",
]
NUMERIC_FIELDS = {"감정가", "최저매각가격", "부채총액", "KB시세"}
BOOL_FIELDS = {"근저당여부", "압류여부", "가압류여부", "가처분여부"}


def norm_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value or "").strip()


def norm_bool(value) -> str:
    text = norm_text(value).lower().replace(" ", "")
    if not text:
        return ""
    yes_tokens = ["예", "y", "yes", "true", "있음", "존재", "소멸"]
    no_tokens = ["아니오", "아니요", "n", "no", "false", "없음", "미존재"]
    if any(token in text for token in yes_tokens):
        return "예"
    if any(token in text for token in no_tokens):
        return "아니오"
    return norm_text(value)


def parse_num(value) -> float:
    text = norm_text(value).replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def compare_value(field: str, gt, pred) -> bool:
    if field in BOOL_FIELDS:
        return norm_bool(gt) == norm_bool(pred)

    if field in NUMERIC_FIELDS:
        gt_num = parse_num(gt)
        pred_num = parse_num(pred)
        if gt_num <= 0 and pred_num <= 0:
            return True
        if gt_num <= 0 or pred_num <= 0:
            return False
        tolerance = max(1.0, gt_num * 0.01)
        return abs(gt_num - pred_num) <= tolerance

    return norm_text(gt) == norm_text(pred)


def evaluate_engine(
    gt_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    key_col: str,
    fields: List[str],
) -> Dict[str, float]:
    gt = gt_df.copy()
    pred = pred_df.copy()

    for col in [key_col] + fields:
        if col not in gt.columns:
            gt[col] = ""
        if col not in pred.columns:
            pred[col] = ""

    gt = gt[[key_col] + fields].copy()
    pred = pred[[key_col] + fields].copy()
    gt[key_col] = gt[key_col].astype(str).str.strip()
    pred[key_col] = pred[key_col].astype(str).str.strip()

    merged = gt.merge(pred, on=key_col, how="left", suffixes=("_gt", "_pred"), indicator=True)
    matched_cases = int((merged["_merge"] == "both").sum())

    summary: Dict[str, float] = {
        "cases_total": float(len(gt)),
        "cases_matched": float(matched_cases),
    }

    per_field_scores = []
    for field in fields:
        correct = 0
        total = len(merged)
        non_empty_pred = 0
        numeric_ape_values = []
        for _, row in merged.iterrows():
            pred_val = row.get(f"{field}_pred")
            if norm_text(pred_val):
                non_empty_pred += 1

            if field in NUMERIC_FIELDS:
                gt_num = parse_num(row.get(f"{field}_gt"))
                pred_num = parse_num(pred_val)
                if gt_num > 0 and pred_num > 0:
                    numeric_ape_values.append(abs(gt_num - pred_num) / gt_num)

            if compare_value(field, row.get(f"{field}_gt"), row.get(f"{field}_pred")):
                correct += 1

        acc = (correct / total) * 100 if total else 0.0
        coverage = (non_empty_pred / total) * 100 if total else 0.0
        mape = (sum(numeric_ape_values) / len(numeric_ape_values) * 100) if numeric_ape_values else 0.0

        summary[f"acc_{field}"] = round(acc, 2)
        summary[f"coverage_{field}"] = round(coverage, 2)
        if field in NUMERIC_FIELDS:
            summary[f"mape_{field}"] = round(mape, 2)
        per_field_scores.append(acc)

    summary["acc_overall"] = round(sum(per_field_scores) / len(per_field_scores), 2) if per_field_scores else 0.0
    return summary


def write_report(
    output_md: Path,
    output_csv: Path,
    gt_path: Path,
    engine_rows: List[Dict[str, float]],
    fields: List[str],
) -> None:
    result_df = pd.DataFrame(engine_rows)
    if not result_df.empty:
        result_df = result_df.sort_values(by=["acc_overall", "cases_matched"], ascending=False)
    result_df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    lines = []
    lines.append("# OCR Engine Benchmark Report")
    lines.append("")
    lines.append(f"- Ground truth: {gt_path}")
    lines.append(f"- Engines compared: {len(result_df)}")
    lines.append("")

    if result_df.empty:
        lines.append("No prediction files found. Add CSV files in data/benchmark/predictions and re-run.")
    else:
        lines.append("## Overall")
        lines.append("")
        for _, row in result_df.iterrows():
            lines.append(
                f"- {row['engine']}: overall {row['acc_overall']}%, "
                f"matched {int(row['cases_matched'])}/{int(row['cases_total'])}"
            )

        lines.append("")
        lines.append("## Field Accuracy")
        lines.append("")
        lines.append("| Engine | " + " | ".join(fields) + " |")
        lines.append("|---|" + "---|" * len(fields))
        for _, row in result_df.iterrows():
            vals = [str(row.get(f"acc_{f}", 0.0)) for f in fields]
            lines.append("| " + str(row["engine"]) + " | " + " | ".join(vals) + " |")

        lines.append("")
        lines.append("## Field Coverage")
        lines.append("")
        lines.append("| Engine | " + " | ".join(fields) + " |")
        lines.append("|---|" + "---|" * len(fields))
        for _, row in result_df.iterrows():
            vals = [str(row.get(f"coverage_{f}", 0.0)) for f in fields]
            lines.append("| " + str(row["engine"]) + " | " + " | ".join(vals) + " |")

        numeric_fields = [f for f in fields if f in NUMERIC_FIELDS]
        if numeric_fields:
            lines.append("")
            lines.append("## Numeric MAPE (Lower is better)")
            lines.append("")
            lines.append("| Engine | " + " | ".join(numeric_fields) + " |")
            lines.append("|---|" + "---|" * len(numeric_fields))
            for _, row in result_df.iterrows():
                vals = [str(row.get(f"mape_{f}", 0.0)) for f in numeric_fields]
                lines.append("| " + str(row["engine"]) + " | " + " | ".join(vals) + " |")

    output_md.write_text("\n".join(lines), encoding="utf-8")


def ensure_template_data(root: Path) -> None:
    benchmark_dir = root / "data" / "benchmark"
    preds_dir = benchmark_dir / "predictions"
    gt_path = benchmark_dir / "ground_truth.csv"

    benchmark_dir.mkdir(parents=True, exist_ok=True)
    preds_dir.mkdir(parents=True, exist_ok=True)

    if not gt_path.exists():
        sample_path = root / "data" / "sample_cases.csv"
        if sample_path.exists():
            sample_df = pd.read_csv(sample_path)
            cols = [c for c in DEFAULT_FIELDS if c in sample_df.columns]
            sample_df[cols].head(20).to_csv(gt_path, index=False, encoding="utf-8-sig")
        else:
            pd.DataFrame(columns=DEFAULT_FIELDS).to_csv(gt_path, index=False, encoding="utf-8-sig")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build OCR engine benchmark report")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--fields", nargs="*", default=DEFAULT_FIELDS)
    args = parser.parse_args()

    root = Path(args.root)
    ensure_template_data(root)

    gt_path = root / "data" / "benchmark" / "ground_truth.csv"
    preds_dir = root / "data" / "benchmark" / "predictions"
    out_dir = root / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    output_csv = out_dir / "ocr_benchmark_summary.csv"
    output_md = out_dir / "ocr_benchmark_report.md"

    gt_df = pd.read_csv(gt_path)
    fields = [f for f in args.fields if f != args.key]

    engine_rows: List[Dict[str, float]] = []
    prediction_files = sorted(preds_dir.glob("*.csv"))

    for pred_path in prediction_files:
        pred_df = pd.read_csv(pred_path)
        summary = evaluate_engine(gt_df, pred_df, args.key, fields)
        summary["engine"] = pred_path.stem
        engine_rows.append(summary)

    write_report(output_md, output_csv, gt_path, engine_rows, fields)

    print(f"Benchmark report written: {output_md}")
    print(f"Summary CSV written: {output_csv}")
    print(f"Prediction files found: {len(prediction_files)}")
    if not prediction_files:
        print("Add prediction CSV files to data/benchmark/predictions (e.g., gemini.csv, local_hybrid.csv).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
