from __future__ import annotations
import csv
import os
from typing import Any

POLICY_REFERENCE = {
    "name": "Auctiscope 운영 정책",
    "objective": "캡처본 입력 후 권리분석까지 완결된 사건만 데이터로 보관하고, 기준 미달 건은 플랫폼이 데이터에서 삭제하며 나머지는 사용자가 삭제할 수 있도록 운영한다.",
    "eligibility_rules": {
        "max_debt_to_kb_ratio": 0.85,
        "max_debt_to_expected_price_ratio": 0.90,
        "min_expected_price_to_debt_ratio": 1.0,
        "require_registry_review_for_risk_flags": True,
        "keep_only_verified_candidates": True,
    },
    "rights_analysis": {
        "source_types": [
            "등기부",
            "시세",
            "채권자 정보",
            "법원 경매 공고",
            "실거래/매물 정보",
            "공공기관 자료"
        ],
        "objective_style": "전문가 수준의 객관적 분석, 과장 금지, 수치와 근거 중심",
        "upgrade_notes": [
            "채권자별 분석 패턴을 계속 업데이트한다.",
            "권리상 하자와 채권자 성향을 분리해 기록한다.",
            "하나의 사건에 대해 근거/리스크/행동안이 명확히 구분되도록 정리한다."
        ],
    },
    "creditor_analysis": {
        "patterns": [
            "1금융: 내부 규정이 엄격하므로 협상 가능성은 낮고, 실질 배당 손실을 숫자로 보여주는 전략이 효과적",
            "2/3금융: 수익과 배당액을 우선하므로 자금 구조와 헤어컷 수치가 중요",
            "유동화/NPL: 신속 회수 선호, 현금성 조건과 조기 상환 제안이 효과적",
            "공공/조세채권: 공공성과 법적 절차가 강해 협의 대상이 제한적"
        ],
        "update_rule": "채권자별 성향, 승인 기준, 협상 포인트는 계속 업데이트해 정책 참조 데이터로 누적한다."
    },
    "data_policy": {
        "keep_data_when": "부채총액 ≤ KB시세×0.85 이고 부채총액 ≤ 낙찰예상가×0.90 이고 권리분석 완료",
        "delete_data_when": "상기 기준을 벗어나거나 취하 진행이 없거나 실무상 부적격으로 판정된 경우",
        "retain_only": "심사결과, 권리분석 요약, 담당자 메모, 스크린샷 저장 기록"
    },
}

YES_SET = {"예", "y", "o", "yes", "true", "1", "o"}
NO_SET = {"아니요", "아니오", "n", "no", "false", "0"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(BASE_DIR, "data", "lender_catalog.csv")


def get_lender_catalog() -> dict[str, Any]:
    """실무형 대주 카탈로그. 데이터 파일이 있으면 그 파일을 기준으로 읽어온다."""
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        lenders = []
        for row in rows:
            lenders.append({
                "name": row.get("name", ""),
                "type": row.get("type", "C"),
                "contact": row.get("contact", ""),
                "email": row.get("email", ""),
                "preferred_regions": [x.strip() for x in row.get("preferred_regions", "").split(";") if x.strip()],
                "preferred_property_types": [x.strip() for x in row.get("preferred_property_types", "").split(";") if x.strip()],
                "max_ltv": float(row.get("max_ltv", "1.0") or 1.0),
                "approval_criteria": [x.strip() for x in row.get("approval_criteria", "").split(";") if x.strip()],
                "verification": {
                    "status": row.get("verification_status", "미확인"),
                    "last_checked": row.get("last_checked", ""),
                    "operational_status": row.get("operational_status", "미확인"),
                },
                "history": [x.strip() for x in row.get("history", "").split(";") if x.strip()],
            })
        return {"lenders": lenders}

    return {
        "lenders": [
            {
                "name": "저축은행 A",
                "type": "A",
                "contact": "02-555-0101",
                "email": "npl@samplebank.co.kr",
                "preferred_regions": ["서울", "경기"],
                "preferred_property_types": ["아파트"],
                "max_ltv": 0.80,
                "approval_criteria": [
                    "권리이슈 없음",
                    "LTV 80% 이하",
                    "수도권 아파트 우선",
                ],
                "verification": {
                    "status": "검증됨",
                    "last_checked": "2026-08-09",
                    "operational_status": "영업중",
                },
                "history": [
                    "2026-07 기준 서울 아파트 브릿지 승인 경험",
                ],
            },
            {
                "name": "대부 B",
                "type": "B",
                "contact": "010-777-0202",
                "email": "bridge@samplefinance.co.kr",
                "preferred_regions": ["서울", "경기", "인천"],
                "preferred_property_types": ["아파트", "오피스텔"],
                "max_ltv": 0.90,
                "approval_criteria": [
                    "권리이슈 1개 이하",
                    "LTV 90% 이하",
                    "신속 심사 가능",
                ],
                "verification": {
                    "status": "검증됨",
                    "last_checked": "2026-08-09",
                    "operational_status": "영업중",
                },
                "history": [
                    "2026-06 기준 고LTV 브릿지 자금 조달 경험",
                ],
            },
            {
                "name": "NPL 전문 C",
                "type": "C",
                "contact": "02-555-0303",
                "email": "nplteam@sampleamc.co.kr",
                "preferred_regions": ["전국"],
                "preferred_property_types": ["아파트", "상가", "토지"],
                "max_ltv": 1.00,
                "approval_criteria": [
                    "권리이슈 2개 이상",
                    "NPL/특수권리 처리 경험",
                    "채권자 헤어컷 협상 가능",
                ],
                "verification": {
                    "status": "검증됨",
                    "last_checked": "2026-08-09",
                    "operational_status": "영업중",
                },
                "history": [
                    "2026-05 기준 특수권리 물건 대위변제 경험",
                ],
            },
        ]
    }

def _is_yes(value: Any) -> bool:
    """연속변수 참/거짓 판정."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in YES_SET:
            return True
        if s in NO_SET:
            return False
        return bool(s)
    return bool(value)

def _safe_float(v: Any) -> float:
    try:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return 0.0
            v = v.replace(",", "")
            v = v.replace(" ", "")
            v = v.replace("\u00a0", "")

            lowered = v.lower()
            if lowered.endswith("억원"):
                number_text = v[:-2].replace("억", "").strip()
                return float(number_text) * 100_000_000
            if lowered.endswith("백만원"):
                number_text = v[:-3].strip()
                return float(number_text) * 1_000_000
            if lowered.endswith("천만원"):
                number_text = v[:-3].strip()
                return float(number_text) * 10_000_000
            if lowered.endswith("만원"):
                number_text = v[:-2].strip()
                return float(number_text) * 10_000
            if lowered.endswith("천원"):
                number_text = v[:-2].strip()
                return float(number_text) * 1_000
            if lowered.endswith("백원"):
                number_text = v[:-2].strip()
                return float(number_text) * 100
            if lowered.endswith("조원"):
                number_text = v[:-2].strip()
                return float(number_text) * 10_000_000_000_000

            v = v.replace("원", "")
            if lowered.endswith("억원"):
                number_text = v[:-2].replace("억", "").strip()
                return float(number_text) * 100_000_000
            if lowered.endswith("백만원"):
                number_text = v[:-3].strip()
                return float(number_text) * 1_000_000
            if lowered.endswith("천만원"):
                number_text = v[:-3].strip()
                return float(number_text) * 10_000_000
            if lowered.endswith("만원"):
                number_text = v[:-2].strip()
                return float(number_text) * 10_000
            if lowered.endswith("천원"):
                number_text = v[:-2].strip()
                return float(number_text) * 1_000
            if lowered.endswith("백원"):
                number_text = v[:-2].strip()
                return float(number_text) * 100
            if lowered.endswith("조원"):
                number_text = v[:-2].strip()
                return float(number_text) * 10_000_000_000_000
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """OCR/입력값 정규화를 수행해 후속 분석의 안정성을 높인다."""
    normalized = {}
    for key, value in row.items():
        if isinstance(value, str):
            normalized[key] = value.strip()
        else:
            normalized[key] = value

    for key in ["사건번호", "법원명", "물건번호", "주소", "아파트명", "주요채권자"]:
        if key in normalized and isinstance(normalized[key], str):
            normalized[key] = normalized[key].strip() or "미상"

    for key in ["감정가", "최저매각가격", "낙찰예상가", "부채총액", "KB시세"]:
        if key in normalized:
            normalized[key] = _safe_float(normalized[key])

    for key in ["청산가능여부", "근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"]:
        if key in normalized and not isinstance(normalized[key], bool):
            normalized[key] = "예" if _is_yes(normalized[key]) else "아니오"

    return normalized


def structure_rights_analysis(row: dict[str, Any]) -> dict[str, Any]:
    """권리분석 결과를 구조화된 형태로 정리해 전문 보고서 형식으로 활용한다."""
    normalized = normalize_row(row)
    rights_flags = []
    for field in ["근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"]:
        if _is_yes(normalized.get(field)):
            rights_flags.append(field)

    creditor = str(normalized.get("주요채권자") or normalized.get("채권자") or "")
    guidance = get_creditor_analysis_guidance(creditor) if creditor else "채권자 정보가 없어 일반 기준으로 평가합니다."

    return {
        "rights_flags": rights_flags,
        "rights_summary": build_rights_summary(normalized),
        "creditor_guidance": guidance,
        "risk_level": "high" if len(rights_flags) >= 2 else "medium" if rights_flags else "low",
    }


def calculate_candidate_score(row: dict[str, Any]) -> int:
    score = 0
    if _is_yes(row.get("청산가능여부")): score += 45
    if _is_yes(row.get("근저당여부")): score -= 10
    if _is_yes(row.get("압류여부")): score -= 12
    if _is_yes(row.get("가압류여부")): score -= 8
    if _is_yes(row.get("가처분여부")): score -= 8
    if _is_yes(row.get("임차권등기여부")): score -= 6
    if _is_yes(row.get("전세권여부")): score -= 6
    if _is_yes(row.get("가등기여부")): score -= 4

    expected_price = _safe_float(row.get("낙찰예상가"))
    debt = _safe_float(row.get("부채총액"))

    if expected_price > 0 and debt > 0:
        ratio = expected_price / debt
        if ratio >= 1.3: score += 30
        elif ratio >= 1.1: score += 18
        elif ratio >= 0.9: score += 8
        else: score -= 12

    if expected_price >= 8_000_000_000:
        score += 17

    return max(0, min(100, int(round(score))))

def classify_grade(score: int) -> str:
    if score >= 80: return "A"
    if score >= 60: return "B"
    return "C"

def recommend_lender(row: dict[str, Any]) -> str:
    """사건의 권리 위험과 자금 구조를 바탕으로 실무적으로 참고할 대응 포인트를 정리합니다."""
    risk_count = 0
    risk_fields = [
        "근저당여부", "압류여부", "가압류여부",
        "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"
    ]
    for f in risk_fields:
        if _is_yes(row.get(f)):
            risk_count += 1

    debt = _safe_float(row.get("부채총액"))
    value = _safe_float(row.get("KB시세") or row.get("감정가"))
    ltv = (debt / value) if value > 0 else 1.0

    region = str(row.get("법원명") or row.get("주소") or "").strip()
    property_type = str(row.get("물건종류") or row.get("아파트명") or "아파트").strip()

    catalog = get_lender_catalog()["lenders"]
    candidates = []
    for lender in catalog:
        if lender["type"] == "A" and (risk_count > 0 or ltv > lender["max_ltv"]):
            continue
        if lender["type"] == "B" and risk_count > 1:
            continue
        if lender["type"] == "C" and risk_count < 2 and ltv < 0.85:
            continue

        region_match = any(token in region for token in lender["preferred_regions"]) if region else True
        property_match = any(token in property_type for token in lender["preferred_property_types"]) if property_type else True
        if not (region_match and property_match):
            continue

        candidates.append(lender)

    if not candidates:
        candidates = catalog

    chosen = candidates[0]
    return (
        f"사건 대응 포인트: {chosen['name']} | 유형: {chosen['type']} | "
        f"참고 연락처: {chosen['contact']} | 이메일: {chosen['email']} | "
        f"검토 상태: {chosen['verification']['status']} | 검토 기준: {', '.join(chosen['approval_criteria'])}"
    )

def get_creditor_advice(creditor: str) -> str:
    """채권자의 성격에 따른 유의사항 및 설득 가이드라인을 반환합니다."""
    if not creditor:
        return "채권자 미상 - 구체적 성향 파악 전까지 유연한 대처가 필요합니다."
    
    c_lower = str(creditor).replace(" ", "").lower()
    
    if any(k in c_lower for k in ["유동화", "에프앤아이", "fni", "npl", "자산관리"]):
        return f"[{creditor}] 유동화/NPL 성향: 신속한 현금회수 선호. 자금 명목수익(헤어컷이나 이자 감면) 조건으로 빠른 상환 제안이 매우 효과적입니다."
    elif any(k in c_lower for k in ["수협", "농협", "중앙회", "은행"]):
        return f"[{creditor}] 1금융 성향: 내부 규정이 엄격하여 협상이 경직적입니다. 전액 상환이나 지연이자 일부 감면 정도로 현실적인 타진을 하십시오."
    elif any(k in c_lower for k in ["저축", "캐피탈", "대부", "파이낸셜"]):
        return f"[{creditor}] 2/3금융 성향: 수익과 배당액을 가장 중시합니다. 경매 진행 시와 낙찰에 따른 현금 배당 손실 리스크(숫자)를 제시하여 자진 취하를 유도하세요."
    elif any(k in c_lower for k in ["세무서", "건강보험", "구청", "시청", "국민연금"]):
        return f"[{creditor}] 공공/조세채권: 법정기일이 빠르면 자금 선순위 불가. 필수 소요자금으로 100% 반영하거나 협의의 분할 납부·압류해제만 가능합니다."
    elif len(c_lower) <= 4: # heuristics for general Korean personal names
        return f"[{creditor}] 개인 채권자 추정: 감정적 대립이 개입되었을 확률이 높습니다. 직접 접촉보다 논리적이고 객관적인 배당액 산정을 바탕으로 대리인 접촉 위주로 진행하십시오."
    else:
        return f"[{creditor}] 기타 채권자: 일반적인 금융권 가이드라인에 따라 접근하되, 추가 상세정보 파악을 권장합니다."

def needs_registry_verification(row: dict[str, Any]) -> bool:
    rights_flags = ["근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"]
    for f in rights_flags:
        if _is_yes(row.get(f)):
            return True

    expected_price = _safe_float(row.get("낙찰예상가"))
    appraisal = _safe_float(row.get("감정가") or row.get("appraisal_price"))
    high_value_cutoff = 2_000_000_000
    if expected_price >= high_value_cutoff or appraisal >= high_value_cutoff:
        return True

    return False

def get_policy_reference() -> dict[str, Any]:
    """운영 정책 및 권리분석 기준 참조본을 반환한다."""
    return POLICY_REFERENCE


def evaluate_case_policy(row: dict[str, Any]) -> dict[str, Any]:
    """경매 건의 정책 준수 여부를 평가하고, 데이터 보관/삭제 판정을 반환한다."""
    debt = _safe_float(row.get("부채총액"))
    kb_price = _safe_float(row.get("KB시세") or row.get("kb_price") or row.get("KB_price"))
    expected_price = _safe_float(row.get("낙찰예상가") or row.get("expected_price"))
    rights_summary = str(row.get("권리요약") or "").strip()
    has_rights_analysis = bool(rights_summary)

    max_kb_ratio = POLICY_REFERENCE["eligibility_rules"]["max_debt_to_kb_ratio"]
    max_expected_ratio = POLICY_REFERENCE["eligibility_rules"]["max_debt_to_expected_price_ratio"]

    kb_ok = True
    expected_ok = True
    if kb_price > 0 and debt > kb_price * max_kb_ratio:
        kb_ok = False
    if expected_price > 0 and debt > expected_price * max_expected_ratio:
        expected_ok = False

    rights_ready = has_rights_analysis
    keep_data = kb_ok and expected_ok and rights_ready

    decision = "keep" if keep_data else "reject"
    return {
        "decision": decision,
        "keep_data": keep_data,
        "reason": (
            "기준 충족" if keep_data else "부채비율/권리분석 기준 미달"
        ),
        "kb_ratio": (debt / kb_price) if kb_price > 0 else None,
        "expected_ratio": (debt / expected_price) if expected_price > 0 else None,
        "rights_ready": rights_ready,
    }


def get_creditor_analysis_guidance(creditor: str) -> str:
    """채권자별 권리분석 및 협상 가이드를 반환한다."""
    if not creditor:
        return "채권자 정보가 없어 일반 기준으로 검토합니다. 채권자별 패턴 누적이 필요합니다."

    c_lower = str(creditor).replace(" ", "").lower()
    if any(k in c_lower for k in ["유동화", "에프앤아이", "fni", "npl", "자산관리"]):
        return "유동화/NPL 성향: 현금 회수 선호. 신속 상환·현금성 조건을 적극적으로 제시하세요."
    if any(k in c_lower for k in ["수협", "농협", "중앙회", "은행"]):
        return "1금융 성향: 규정이 엄격하므로 실질 배당 손실을 숫자로 제시하는 방식이 효과적입니다."
    if any(k in c_lower for k in ["저축", "캐피탈", "대부", "파이낸셜"]):
        return "2/3금융 성향: 수익과 배당액 논리를 우선해야 하며, 헤어컷 수치와 자금구조 설명이 중요합니다."
    if any(k in c_lower for k in ["세무서", "건강보험", "구청", "시청", "국민연금"]):
        return "공공/조세채권 성향: 협의 범위가 제한적이므로 법적 절차와 현금 회수 리스크를 명확히 보여줘야 합니다."
    return "기타 채권자: 채권자별 성향 업데이트를 계속 반영해 판단 근거를 축적하세요."


def _choose_kb_threshold(row: dict[str, Any]) -> float:
    risk_count = 0
    rights_flags = ["근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"]
    for f in rights_flags:
        if _is_yes(row.get(f)):
            risk_count += 1
    
    expected_price = _safe_float(row.get("낙찰예상가"))
    debt = _safe_float(row.get("부채총액"))

    if debt > 0 and expected_price > 0 and expected_price / debt < 1.0:
        risk_count += 1

    return 0.80 if risk_count >= 2 else 0.85

def passes_market_filters(row: dict[str, Any]) -> bool:
    debt = _safe_float(row.get("부채총액"))
    if debt <= 0:
        return False

    kb_price = _safe_float(row.get("KB시세") or row.get("kb_price") or row.get("KB_price"))
    if kb_price > 0:
        threshold = _choose_kb_threshold(row)
        if debt <= kb_price * threshold:
            return True
        if debt >= kb_price * 0.85:
            return False

    appraisal = _safe_float(row.get("감정가") or row.get("appraisal_price"))
    expected_price = _safe_float(row.get("낙찰예상가") or row.get("expected_price"))

    if appraisal > 0 and debt <= appraisal * 0.9:
        return True
    if expected_price > 0 and debt <= expected_price * 0.9:
        return True

    return False

def build_rights_summary(row: dict[str, Any]) -> str:
    parts = []
    if _is_yes(row.get("근저당여부")): parts.append("근저당 존재")
    if _is_yes(row.get("압류여부")): parts.append("압류 존재")
    if _is_yes(row.get("가압류여부")): parts.append("가압류 존재")
    if _is_yes(row.get("가처분여부")): parts.append("가처분 존재")
    if _is_yes(row.get("임차권등기여부")): parts.append("임차권등기 존재")
    if _is_yes(row.get("전세권여부")): parts.append("전세권 존재")
    if _is_yes(row.get("가등기여부")): parts.append("가등기 존재")

    if not parts:
        return "권리 이슈 없음. 실무상 추가 확인이 필요하지 않은 구조로 보입니다."

    creditor = str(row.get("주요채권자") or row.get("채권자") or "")
    guidance = get_creditor_analysis_guidance(creditor) if creditor else ""
    risk_clause = "; ".join(parts)
    if guidance:
        return f"{risk_clause}. {guidance}"
    return risk_clause

def suggest_candidate_flag(row: dict[str, Any]) -> str:
    score = _safe_float(row.get("분석점수"))
    grade = str(row.get("분석등급") or "").upper()
    if grade == "A" or score >= 80:
        return "✔️"
    return ""

def build_visit_advice(row: dict[str, Any]) -> str:
    score = _safe_float(row.get("분석점수"))
    grade = str(row.get("분석등급") or "").upper()
    if grade == "A" or score >= 85:
        return "방문 접근성이 비교적 양호할 가능성이 높습니다. 소유주와 직접 만나기 쉬운 지역에 위치해 있어, 실질적인 협의가 이어질 가능성이 큽니다."
    if grade == "B" or score >= 70:
        return "방문을 시도할 가치가 있지만, 사전 연락과 권리사항 설명이 충분히 준비된 후에 가는 것이 더 효과적입니다."
    return "방문 전 추가 자료나 권리 확인이 먼저 필요하므로, 우선 사전 연락과 자료 정리를 마친 뒤 방문하는 것이 보다 효율적입니다."

def build_phone_pitch(row: dict[str, Any]) -> str:
    score = _safe_float(row.get("분석점수"))
    grade = str(row.get("분석등급") or "").upper()
    if grade == "A" or score >= 85:
        return "전화로도 충분한 설명이 가능할 정도로, 이 물건은 정리 가능성과 실무진 검토 통과 가능성이 높아 보입니다. 소유주에게는 부담을 줄이는 방향으로 설명하는 것이 좋습니다."
    if grade == "B" or score >= 70:
        return "전화로 먼저 기본 흐름을 설명하고, 필요한 자료를 정리해 함께 검토하는 방식이 더 안정적입니다. 소유주가 판단할 수 있는 기준을 먼저 제시하는 것이 좋습니다."
    return "전화 상담은 보조적으로 활용하고, 권리와 자금 구조가 정리된 후에 다시 접촉하는 방식이 낫습니다. 먼저 자료를 정리해 처리하는 것이 좋습니다."

def build_visit_pitch(row: dict[str, Any]) -> str:
    score = _safe_float(row.get("분석점수"))
    grade = str(row.get("분석등급") or "").upper()
    if grade == "A" or score >= 85:
        return "현장 방문을 이 물건의 실질적인 정리 가능성을 소유주에게 직접 설명하기에 적합합니다. 사전 준비된 자료와 함께 가면 협의가 빠르게 진행될 가능성이 높습니다."
    if grade == "B" or score >= 70:
        return "현장 방문은 일정 부분 효과적이지만, 권리사항과 협의안에 대한 설명을 먼저 정리하고 가는 것이 좋습니다. 소유주가 이해하기 쉬운 흐름으로 접근하는 것이 중요합니다."
    return "현장 방문 전에는 권리 확인이 충분히 선행되어야 하므로, 자료 정리와 사전 안내를 마친 뒤 방문하는 방식이 더 안전합니다."

def build_owner_pitch(row: dict[str, Any]) -> str:
    score = _safe_float(row.get("분석점수"))
    grade = str(row.get("분석등급") or "").upper()
    expected_price = _safe_float(row.get("낙찰예상가"))
    debt = _safe_float(row.get("부채총액"))

    if grade == "A" or score >= 85:
        base = "이 물건은 권리구조와 청산 가능성이 비교적 안정적이라, 소유주 입장에서도 부담을 줄이면서 빠르게 정리할 수 있는 방안이 될 수 있습니다."
    elif grade == "B" or score >= 70:
        base = "이 물건은 일부 권리 이슈가 있지만, 현실적인 협의안과 자금 구조를 함께 설명하면 소유주도 충분히 검토할 수 있는 수준입니다."
    else:
        base = "이 물건은 추가 확인이 필요한 부분이 있어, 소유주와의 협의 전에 권리와 자금 구조를 먼저 정리하는 방식이 더 안전합니다."

    if expected_price > 0 and debt > 0:
        ratio = expected_price / debt
        if ratio >= 1.1:
            base += f" 특히 예상 낙찰가가 부채 대비 {ratio:.1f}배 수준으로, 정리 가능성이 있는 구조로 보여 현재 방식으로 접근해볼 만합니다."
        else:
            base += " 다만 예상 낙찰가와 부채 규모를 함께 설명해 현실적인 협의안으로 접근하는 것이 중요합니다."
    
    creditor = str(row.get('주요채권자') or row.get('채권자') or '')
    if creditor:
        base += '\n\n[채권자 협상 가이드]\n' + get_creditor_advice(creditor)

    return base

