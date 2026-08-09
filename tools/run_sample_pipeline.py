import os
import logging
from datetime import datetime
from io import BytesIO
import pandas as pd
from analysis import (
    calculate_candidate_score,
    classify_grade,
    recommend_lender,
    build_rights_summary,
    suggest_candidate_flag,
    build_owner_pitch,
    build_visit_advice,
    passes_market_filters,
    needs_registry_verification,
    evaluate_case_policy,
)

# PPT/PDF helpers
from report_generator import generate_pptx_bytes, generate_pdf_bytes

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(OUT_DIR, exist_ok=True)
DELETED_DIR = os.path.join(OUT_DIR, "deleted")
os.makedirs(DELETED_DIR, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def process_file(csv_path: str):
    logger.info("Loading sample CSV: %s", csv_path)
    df = pd.read_csv(csv_path)
    keep_rows = []
    deleted_rows = []

    for _, row in df.iterrows():
        r = row.to_dict()
        score = calculate_candidate_score(r)
        grade = classify_grade(score)
        r["분석점수"] = score
        r["분석등급"] = grade
        if not (r.get("권리요약")):
            r["권리요약"] = build_rights_summary(r)
        if not (r.get("추천대주")):
            r["추천대주"] = recommend_lender({"분석점수": score, "분석등급": grade})

        try:
            policy_eval = evaluate_case_policy(r)
            market_ok = passes_market_filters(r) and policy_eval.get("keep_data", False)
        except Exception:
            policy_eval = {"decision": "reject", "keep_data": False, "reason": "정책평가 실패"}
            market_ok = False

        if not market_ok:
            # schedule for deletion (by default move to outputs/deleted for audit)
            deleted_rows.append({**r, "심사결과": policy_eval.get("reason", "기준 미달")})
            continue

        if needs_registry_verification(r):
            r["등기부열람여부"] = r.get("등기부열람여부") or "요청"

        r["담당자메모"] = f"최종 의견:\n- {build_owner_pitch(r)}\n- {build_visit_advice(r)}"
        keep_rows.append(r)

    # Save outputs
    out_df = pd.DataFrame(keep_rows)
    out_path = os.path.join(OUT_DIR, "processed.xlsx")
    out_df.to_excel(out_path, index=False)
    logger.info("Processed saved to: %s", out_path)

    # Export PPT/PDF for top N (by 분석점수)
    top_rows = sorted(keep_rows, key=lambda x: x.get("분석점수", 0), reverse=True)[:10]
    pptb = generate_pptx_bytes(top_rows)
    pdfb = generate_pdf_bytes(top_rows)
    with open(os.path.join(OUT_DIR, "top10.pptx"), "wb") as f:
        f.write(pptb)
    with open(os.path.join(OUT_DIR, "top10.pdf"), "wb") as f:
        f.write(pdfb)
    logger.info("Exported PPTX and PDF to %s", OUT_DIR)

    logger.info("Total input rows: %d", len(df))
    logger.info("Kept rows: %d", len(keep_rows))

    # Handle deleted rows: by default move to deleted folder with timestamp for audit.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    deleted_count = len(deleted_rows)
    if deleted_count:
        deleted_df = pd.DataFrame(deleted_rows)
        deleted_path = os.path.join(DELETED_DIR, f"deleted_{ts}.csv")

        # Respect environment override for permanent deletion
        permanent = os.environ.get("PERMANENT_DELETE", "0").lower() in ("1", "true", "yes")
        if permanent:
            # permanent deletion: do not save deleted rows
            logger.warning("PERMANENT_DELETE enabled — %d rows will be permanently discarded", deleted_count)
        else:
            deleted_df.to_csv(deleted_path, index=False)
            logger.info("Moved %d deleted rows to: %s", deleted_count, deleted_path)

    logger.info("Auto-deleted rows: %d", deleted_count)


if __name__ == '__main__':
    sample_path = os.path.join(os.path.dirname(__file__), "..", "data", "sample_cases.csv")
    process_file(sample_path)
