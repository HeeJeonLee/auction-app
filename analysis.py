from __future__ import annotations
from typing import Any

YES_SET = {"예", "y", "o", "yes", "true", "1", "o"}
NO_SET = {"아니요", "아니오", "n", "no", "false", "0"}

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
            v = v.replace(",", "")
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0

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
    """물건의 권리 위험과 부채 현황(LTV)을 바탕으로 대주를 추천합니다."""
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

    if risk_count == 0 and ltv <= 0.82:
        return "A타입 (1금융 대환 타겟) | 추천: 🟢🟢저축은행(02-XXX-XXXX), 담당자 김모모 팀장"
    elif risk_count <= 1 and ltv <= 0.90:
        return "B타입 (고LTV 공격적 대주) | 추천: 🔵🔵대부(02-YYY-YYYY), 담당자 박모모 이사"
    else:
        return "C타입 (특수물건·NPL 전문 대주) | 추천: 🔴🔴NPL자산관리(02-ZZZ-ZZZZ), 담당자 최모모 대표"

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
        return f"[{creditor}] 개인 채권자 추정: 감정적 대립이 개입되었을 확률이 높습니다. 직접 접촉보다 논리적이고 객관적인 배당액 산정을 바탕으로 대리인(대주 측) 접촉 위주로 진행하십시오."
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
    
    return "; ".join(parts) if parts else "권리 이슈 없음"

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

