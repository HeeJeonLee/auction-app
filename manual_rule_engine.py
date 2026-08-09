from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RULEPACK = BASE_DIR / "data" / "manual_rules_mvp_v1.json"


def _safe_float(value: Any) -> float:
    try:
        if isinstance(value, str):
            text = value.strip().replace(",", "").replace("원", "")
            if not text:
                return 0.0
            return float(text)
        return float(value or 0)
    except Exception:
        return 0.0


@lru_cache(maxsize=8)
def _load_rulepack_cached(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    if not path.exists():
        return {
            "rule_version": "MVP-UNAVAILABLE",
            "base_score": 0,
            "score_bounds": {"min": 0, "max": 100},
            "verdict_thresholds": {"go": 80, "hold": 60},
            "rules": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def load_rulepack(path: Path | None = None) -> dict[str, Any]:
    rule_path = path or DEFAULT_RULEPACK
    return _load_rulepack_cached(str(rule_path))


def _pick_region_text(row: dict[str, Any]) -> str:
    return str(row.get("법원명") or "") + " " + str(row.get("주소") or "")


def _count_rights_flags(row: dict[str, Any]) -> int:
    keys = ["근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"]
    count = 0
    for key in keys:
        text = str(row.get(key) or "").strip()
        if text in {"예", "Y", "yes", "Yes", "true", "1"}:
            count += 1
    return count


def _eval_rule(rule: dict[str, Any], row: dict[str, Any]) -> tuple[bool, str]:
    op = str(rule.get("operator") or "").strip()
    field = str(rule.get("field") or "")
    value = rule.get("value")

    if op == "exists":
        raw = str(row.get(field) or "").strip()
        return (bool(raw), raw or "")

    if op == "numeric_exists":
        num = _safe_float(row.get(field))
        return (num > 0, str(num))

    if op == "numeric_gte":
        num = _safe_float(row.get(field))
        threshold = _safe_float(value)
        return (num >= threshold, f"{num} >= {threshold}")

    if op == "numeric_lte":
        num = _safe_float(row.get(field))
        threshold = _safe_float(value)
        return (num <= threshold, f"{num} <= {threshold}")

    if op == "region_allowed":
        region_text = _pick_region_text(row)
        tokens = [str(x) for x in (value or [])]
        matched = [t for t in tokens if t and t in region_text]
        return (len(matched) > 0, ",".join(matched) if matched else region_text)

    if op == "ltv_max":
        debt = _safe_float(row.get("부채총액"))
        kb = _safe_float(row.get("KB시세") or row.get("감정가"))
        ltv = (debt / kb) if kb > 0 else 9.9
        max_ltv = float(value or 0.85)
        return (ltv <= max_ltv, f"ltv={ltv:.3f},max={max_ltv:.3f}")

    if op == "risk_flags_max":
        count = _count_rights_flags(row)
        max_count = int(value or 3)
        return (count <= max_count, f"risk_flags={count},max={max_count}")

    if op == "bool_yes_penalty":
        text = str(row.get(field) or "").strip()
        is_yes = text in {"예", "Y", "yes", "Yes", "true", "1"}
        # risk_penalty에서는 True가 페널티 조건이다.
        return (not is_yes, text)

    return (True, "unsupported-op")


def _build_withdrawal_script(row: dict[str, Any], verdict: str, risks: list[str], rule_version: str) -> str:
    creditor = str(row.get("주요채권자") or "미상")
    creditor_tag = "일반"
    c = creditor.replace(" ", "")
    if any(k in c for k in ["은행", "농협", "수협", "중앙회"]):
        creditor_tag = "1금융"
    elif any(k in c for k in ["저축", "캐피탈", "대부", "파이낸셜"]):
        creditor_tag = "2/3금융"
    elif any(k in c for k in ["유동화", "NPL", "npl", "자산관리"]):
        creditor_tag = "유동화/NPL"
    elif any(k in c for k in ["세무서", "구청", "시청", "건강보험"]):
        creditor_tag = "공공"

    risk_text = ", ".join(risks[:3]) if risks else "핵심 리스크 없음"
    if verdict == "GO":
        tone = "회수 개선 수치를 먼저 제시하고, 기한/증빙 조건을 명확히 합의"
    elif verdict == "HOLD":
        tone = "보완자료 확보 후 조건부 제안으로 접근"
    else:
        tone = "즉시 취하 유도보다 리스크 해소 계획을 먼저 제시"

    return (
        f"[규칙버전 {rule_version}] 채권자유형={creditor_tag}, 대상={creditor}\n"
        f"- 현재 판단: {verdict} / 핵심리스크: {risk_text}\n"
        f"- 접근전략: {tone}\n"
        "- 기본 문구: '경매 지속 대비 회수액·회수시점 개선안을 수치로 제시드리며, 이행증빙과 기한을 함께 확정하겠습니다.'"
    )


def evaluate_manual_rules(row: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    rulepack = load_rulepack(path)
    rules = list(rulepack.get("rules") or [])

    score = int(rulepack.get("base_score") or 0)
    min_score = int((rulepack.get("score_bounds") or {}).get("min", 0))
    max_score = int((rulepack.get("score_bounds") or {}).get("max", 100))

    risks: list[str] = []
    recommendations: list[str] = []
    evidences: list[str] = []

    for rule in rules:
        passed, evidence = _eval_rule(rule, row)
        rid = str(rule.get("id") or "RULE")
        field = str(rule.get("field") or "")
        weight = int(rule.get("weight") or 0)
        mode = str(rule.get("mode") or "must_pass")

        evidences.append(f"{rid}:{field}={evidence}")

        if mode == "risk_penalty":
            if not passed:
                score -= weight
                risks.append(str(rule.get("risk_label") or rid))
                recommendations.append(str(rule.get("recommendation") or ""))
            continue

        if passed:
            score += max(1, weight // 3)
        else:
            score -= weight
            risks.append(str(rule.get("risk_label") or rid))
            recommendations.append(str(rule.get("recommendation") or ""))

    score = max(min_score, min(max_score, score))

    thresholds = rulepack.get("verdict_thresholds") or {}
    go = int(thresholds.get("go", 75))
    hold = int(thresholds.get("hold", 55))

    if score >= go:
        verdict = "GO"
    elif score >= hold:
        verdict = "HOLD"
    else:
        verdict = "DROP"

    script = _build_withdrawal_script(row, verdict, risks, str(rulepack.get("rule_version") or "MVP"))

    return {
        "rule_version": str(rulepack.get("rule_version") or "MVP"),
        "score": score,
        "verdict": verdict,
        "risks": risks,
        "recommendations": recommendations[:5],
        "evidence": evidences[:12],
        "withdrawal_script": script,
    }
