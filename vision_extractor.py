import os
import json
import io
import time
import re
import warnings
from typing import List, Any

import pandas as pd
from PIL import Image
from PIL import ImageFilter
from PIL import ImageOps

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None

try:
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover - optional dependency
    PaddleOCR = None

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    try:
        import google.generativeai as genai
    except Exception:  # pragma: no cover - 환경에 패키지가 없을 수 있음
        genai = None

from analysis import _safe_float, get_creditor_analysis_guidance, structure_rights_analysis


_PADDLE_OCR_INSTANCE = None


def _decide_quality_profile(width: int, height: int, edge_score: float, contrast: float) -> str:
    aspect = (height / width) if width else 1.0
    if aspect >= 1.9:
        return "mobile_long"
    if edge_score >= 0.08 and contrast >= 0.18:
        return "table_dense"
    return "mixed_ui"


def _recommended_quality_threshold(profile: str) -> int:
    if profile == "table_dense":
        return 68
    if profile == "mobile_long":
        return 60
    return 64


def assess_image_quality(image_bytes: bytes) -> dict[str, Any]:
    """이미지 품질 지표를 계산하고 문서 유형별 임계값으로 재촬영 필요 여부를 판단한다."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        gray = img.resize((200, 200))
        pixels = list(gray.get_flattened_data())
        mean_pixel = sum(pixels) / max(1, len(pixels))
        mean_brightness = mean_pixel / 255.0
        variance = sum((p - mean_pixel) ** 2 for p in pixels) / max(1, len(pixels))
        contrast = (variance ** 0.5) / 255.0
        edge_score = 0.0
        for i in range(1, gray.width - 1):
            for j in range(1, gray.height - 1):
                diff = abs(gray.getpixel((i, j)) - gray.getpixel((i - 1, j))) + abs(gray.getpixel((i, j)) - gray.getpixel((i, j - 1)))
                edge_score += diff
        edge_score /= (gray.width * gray.height * 255 * 2)

        profile = _decide_quality_profile(img.width, img.height, edge_score, contrast)
        recommended_min_score = _recommended_quality_threshold(profile)

        score = 82
        if mean_brightness < 0.22:
            score -= 26
        elif mean_brightness < 0.32:
            score -= 14
        elif mean_brightness > 0.90:
            score -= 12

        if contrast < 0.10:
            score -= 22
        elif contrast < 0.15:
            score -= 12

        if edge_score < 0.03:
            score -= 22
        elif edge_score < 0.05:
            score -= 12

        score = max(0, min(100, score))
        return {
            "score": int(score),
            "brightness": round(mean_brightness, 3),
            "variance": round(variance, 3),
            "contrast": round(contrast, 3),
            "edge_score": round(edge_score, 3),
            "profile": profile,
            "recommended_min_score": recommended_min_score,
            "needs_recapture": score < recommended_min_score,
        }
    except Exception:
        return {
            "score": 50,
            "brightness": 0.5,
            "variance": 0.0,
            "contrast": 0.0,
            "edge_score": 0.0,
            "profile": "mixed_ui",
            "recommended_min_score": 64,
            "needs_recapture": True,
        }


def build_recapture_guidance(quality: dict[str, Any]) -> str:
    profile = str(quality.get("profile") or "mixed_ui")
    threshold = int(quality.get("recommended_min_score") or 64)

    if quality.get("needs_recapture"):
        if profile == "mobile_long":
            return (
                f"캡처 보정 권장(긴 모바일 캡처 기준 {threshold}점): "
                "스크롤 캡처는 글자 높이를 키우고, 화면 확대(125~150%) 후 다시 캡처하면 인식률이 개선됩니다."
            )
        if profile == "table_dense":
            return (
                f"캡처 보정 권장(표 밀집 문서 기준 {threshold}점): "
                "표 선과 숫자가 뭉개지지 않도록 원본 해상도로 저장하고, 밝기를 조금 올려 재업로드해 주세요."
            )
        return (
            f"캡처 보정 권장(기준 {threshold}점): "
            "문서가 너무 어둡거나 흐릿하거나 잘려 보이면 화면을 선명하게 한 뒤 다시 업로드해 주세요."
        )
    return f"품질 양호(기준 {threshold}점 이상): OCR 및 자동 정리 단계로 바로 진행해도 좋습니다."


def detect_missing_fields(row: dict[str, Any]) -> list[str]:
    """권리분석에 꼭 필요한 핵심 필드가 누락됐는지 검사한다."""
    required_fields = [
        "사건번호",
        "법원명",
        "아파트명",
        "주소",
        "감정가",
        "부채총액",
        "KB시세",
        "주요채권자",
        "근저당여부",
    ]
    missing = []
    for field in required_fields:
        value = row.get(field, "")
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def build_structured_case_summary(row: dict[str, Any]) -> dict[str, Any]:
    """OCR/입력값을 정리해 권리분석으로 바로 이어지도록 구조화한다."""
    normalized = {}
    for key, value in row.items():
        if isinstance(value, str):
            normalized[key] = value.strip()
        else:
            normalized[key] = value

    debt = _safe_float(normalized.get("부채총액"))
    kb = _safe_float(normalized.get("KB시세"))
    appraisal = _safe_float(normalized.get("감정가"))
    expected = _safe_float(normalized.get("낙찰예상가"))
    creditor = str(normalized.get("주요채권자") or normalized.get("채권자") or "")

    rights = structure_rights_analysis(normalized)
    summary_parts = []
    if normalized.get("아파트명"):
        summary_parts.append(f"{normalized['아파트명']}")
    if normalized.get("주소"):
        summary_parts.append(f"{normalized['주소']}")
    if normalized.get("법원명"):
        summary_parts.append(f"{normalized['법원명']} 기준")
    if normalized.get("사건번호"):
        summary_parts.append(f"사건번호 {normalized['사건번호']}")

    summary = " / ".join(summary_parts) if summary_parts else "입력된 경매 물건 정보"
    summary += f". 부채총액 {debt:,.0f}원, KB시세 {kb:,.0f}원, 감정가 {appraisal:,.0f}원, 예상낙찰가 {expected:,.0f}원 기준으로 정리했습니다."

    missing_fields = detect_missing_fields(normalized)
    completion_score = 70
    if normalized.get("사건번호"):
        completion_score += 5
    if normalized.get("아파트명"):
        completion_score += 5
    if normalized.get("주소"):
        completion_score += 5
    if creditor:
        completion_score += 5
    if rights["rights_flags"]:
        completion_score += 5
    completion_score -= min(20, len(missing_fields) * 5)

    status = "완료" if completion_score >= 85 else "보완필요"
    return {
        "정리상태": status,
        "완성도": min(100, max(0, completion_score)),
        "자동정리요약": summary,
        "권리플래그": rights["rights_flags"],
        "채권자가이드": get_creditor_analysis_guidance(creditor),
        "누락필드": missing_fields,
    }


def build_case_briefing(row: dict[str, Any]) -> str:
    """설득자료용 1페이지 요약문을 만든다."""
    summary = build_structured_case_summary(row)
    creditor = summary["채권자가이드"]
    rights = ", ".join(summary["권리플래그"]) if summary["권리플래그"] else "권리이슈 없음"
    missing_fields = ", ".join(summary.get("누락필드", [])) if summary.get("누락필드") else "없음"
    return (
        f"{summary['자동정리요약']}\n"
        f"권리 관점: {rights}.\n"
        f"협상 포인트: {creditor}\n"
        f"보완 필요 필드: {missing_fields}\n"
        f"실무 추천: 캡처본의 핵심 사실을 기준으로 권리분석과 채권자 대응 포인트를 먼저 정리한 뒤, 소유주와 이해관계자에게 설득 가능한 흐름으로 제시하세요."
    )


def _is_rate_limited_error(error: Exception) -> bool:
    message = str(error).lower()
    tokens = [
        "rate_limit_exceeded",
        "quota exceeded",
        "quota exceeded for quota metric",
        "resource_exhausted",
        "429",
    ]
    return any(token in message for token in tokens)


def _build_quota_fallback_dataframe(image_files: List[Any], default_columns: List[str], detail: str) -> pd.DataFrame:
    """Gemini 호출 한도 초과 시 분석 중단 없이 보류 데이터로 반환한다."""
    extracted_rows = []
    for img in image_files:
        row = {col: "" for col in default_columns}
        row["원본파일명"] = getattr(img, "name", "미상")
        row["사건번호"] = "AI쿼터대기"
        row["AI_심층분석"] = detail
        row["담당자메모"] = (
            "▶ Gemini 분당 요청 한도 초과로 자동 판독이 일시 보류되었습니다. "
            "앱이 내부적으로 65초 대기 재시도까지 수행했지만 한도 회복이 되지 않았습니다. "
            "잠시 후 다시 실행하거나 CSV/XLSX 업로드로 먼저 심사를 진행해 주세요."
        )
        row["심사상태"] = "보완필요(쿼터초과)"

        auto_summary = build_structured_case_summary(row)
        row["권리요약"] = auto_summary["자동정리요약"]
        extracted_rows.append(row)

    return pd.DataFrame(extracted_rows)


def _extract_json_array_text(raw_text: str) -> str:
    """응답에 설명 문장이 섞여 있어도 JSON 배열/객체 본문만 최대한 복원한다."""
    text = (raw_text or "").replace("```json", "").replace("```", "").strip()
    if not text:
        return ""

    # 가장 먼저 배열 형태를 찾고, 없으면 객체를 배열로 감싼다.
    arr_match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if arr_match:
        return arr_match.group(0).strip()

    obj_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if obj_match:
        return f"[{obj_match.group(0).strip()}]"

    return text


def _build_image_parts_for_mode(image_name: str, image_bytes: bytes, mode: str) -> list[Any]:
    """인식 모드에 맞는 이미지 파트를 생성한다.

    mode="text_first"인 경우, 색상/사진 요소 영향을 줄이기 위해
    고대비 흑백 전처리와 세로 분할을 적용한다.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    parts: list[Any] = []

    if mode == "text_first":
        # 텍스트 레이어 강화: 고대비 + 샤픈 + 이진화
        gray = ImageOps.grayscale(img)
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.SHARPEN)
        bw = gray.point(lambda p: 255 if p > 145 else 0)

        # 긴 모바일 캡처는 1회 호출 내에서 세로 분할 이미지로 전달
        max_h = 1400
        overlap = 180
        w, h = bw.size
        y = 0
        strip_idx = 1
        while y < h:
            y2 = min(h, y + max_h)
            crop = bw.crop((0, y, w, y2))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            parts.append({"mime_type": "image/png", "data": buf.getvalue()})
            parts.append(f"[분할영역 {strip_idx}] 문장/표 텍스트만 우선 판독하세요.")
            if y2 >= h:
                break
            y = y2 - overlap
            strip_idx += 1
    else:
        ext = image_name.lower()
        mime_type = "image/jpeg" if ext.endswith(("jpg", "jpeg")) else "image/png"
        parts.append({"mime_type": mime_type, "data": image_bytes})

    return parts


def _to_rows(parsed_data: Any, image_name: str, default_columns: List[str]) -> list[dict[str, Any]]:
    """모델 파싱 결과를 표준 행 리스트로 변환한다."""
    if isinstance(parsed_data, dict):
        parsed_data = [parsed_data]
    if not isinstance(parsed_data, list):
        parsed_data = []

    rows = []
    for data in parsed_data:
        row = {col: "" for col in default_columns}
        if isinstance(data, dict):
            for key, value in data.items():
                if key in row:
                    row[key] = value
            if not row.get("원본파일명"):
                row["원본파일명"] = image_name
            row["AI_심층분석"] = data.get("AI_심층분석", "")
            row = _apply_registry_entries(row, data)
        else:
            row["원본파일명"] = image_name
            row["사건번호"] = "판독불가"
            row["AI_심층분석"] = "[오류] AI 결과 형식이 비정상이라 기본 행으로 대체되었습니다."

        row = _normalize_extracted_row(row)
        auto_summary = build_structured_case_summary(row)
        row["권리요약"] = auto_summary["자동정리요약"]
        row["담당자메모"] = build_case_briefing(row)
        row["심사상태"] = auto_summary["정리상태"]
        rows.append(row)

    if not rows:
        row = {col: "" for col in default_columns}
        row["원본파일명"] = image_name
        row["사건번호"] = "정보없음"
        row["AI_심층분석"] = "[경고] AI가 이미지에서 경매 정보를 충분히 추출하지 못했습니다."
        row = _normalize_extracted_row(row)
        auto_summary = build_structured_case_summary(row)
        row["권리요약"] = auto_summary["자동정리요약"]
        row["담당자메모"] = build_case_briefing(row)
        row["심사상태"] = auto_summary["정리상태"]
        rows.append(row)

    return rows


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_case_number(value: Any) -> str:
    text = _norm_text(value)
    if not text:
        return ""

    compact = re.sub(r"\s+", "", text)
    m = re.search(r"(\d{4})타경(\d{2,10})", compact)
    if m:
        return f"{m.group(1)}타경{m.group(2)}"

    m = re.search(r"(\d{4})타{0,1}경(\d{2,10})", compact)
    if m:
        return f"{m.group(1)}타경{m.group(2)}"

    return compact


def _normalize_yes_no(value: Any) -> str:
    text = _norm_text(value).lower().replace(" ", "")
    if not text:
        return ""
    yes_tokens = ["예", "y", "yes", "true", "있음", "존재", "소멸"]
    no_tokens = ["아니오", "아니요", "n", "no", "false", "없음", "미존재"]
    if any(token in text for token in yes_tokens):
        return "예"
    if any(token in text for token in no_tokens):
        return "아니오"
    return _norm_text(value)


def _normalize_amount_text(value: Any) -> str:
    text = _norm_text(value)
    if not text:
        return ""

    if any(unit in text for unit in ["억", "만", "천", "원"]):
        return text.replace(" ", "")

    m = re.search(r"(\d[\d,]{2,})", text)
    if m:
        return m.group(1).replace(",", "")

    return text


def _normalize_extracted_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)

    normalized["사건번호"] = _normalize_case_number(normalized.get("사건번호"))
    if "관련사건번호" in normalized:
        normalized["관련사건번호"] = _normalize_case_number(normalized.get("관련사건번호"))

    for field in ["감정가", "최저매각가격", "낙찰예상가", "부채총액", "KB시세"]:
        if field in normalized:
            normalized[field] = _normalize_amount_text(normalized.get(field))

    for field in ["청산가능여부", "근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"]:
        if field in normalized:
            normalized[field] = _normalize_yes_no(normalized.get(field))

    for field in ["법원명", "아파트명", "주요채권자", "주소", "물건번호"]:
        if field in normalized:
            normalized[field] = re.sub(r"\s+", " ", _norm_text(normalized.get(field)))

    return normalized


def _normalize_registry_entries(raw_entries: Any) -> list[dict[str, Any]]:
    """권리항목목록 필드를 표준 dict 리스트로 정규화한다."""
    if raw_entries is None:
        return []

    entries = raw_entries
    if isinstance(raw_entries, str):
        text = raw_entries.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                entries = json.loads(text)
            except Exception:
                entries = []

    if not isinstance(entries, list):
        return []

    result = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        result.append({
            "종류": _norm_text(e.get("종류") or e.get("type")),
            "권리자": _norm_text(e.get("권리자") or e.get("holder") or e.get("creditor")),
            "금액": _normalize_amount_text(e.get("금액") or e.get("amount") or e.get("채권금액")),
            "소멸": _norm_text(e.get("소멸") or e.get("extinct")),
            "접수": _norm_text(e.get("접수") or e.get("접수일") or e.get("date")),
        })
    return result


def _apply_registry_entries(row: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """등기표 구조 데이터를 읽어 권리 플래그/채권자/부채 추정치를 보강한다."""
    enriched = dict(row)

    raw_entries = (
        data.get("권리항목목록")
        or data.get("rights_entries")
        or data.get("registry_entries")
    )
    entries = _normalize_registry_entries(raw_entries)
    if not entries:
        return enriched

    claim_sum = 0.0
    main_creditor = _norm_text(enriched.get("주요채권자"))

    for entry in entries:
        kind = entry["종류"]
        holder = entry["권리자"]
        amount = _safe_float(entry["금액"])

        if not main_creditor and holder:
            main_creditor = holder

        if "근저당" in kind:
            enriched["근저당여부"] = "예"
            claim_sum += amount
        if "가압류" in kind:
            enriched["가압류여부"] = "예"
            claim_sum += amount
        if "가처분" in kind:
            enriched["가처분여부"] = "예"
        if "압류" in kind and "가압류" not in kind:
            enriched["압류여부"] = "예"
        if "임차권" in kind:
            enriched["임차권등기여부"] = "예"
            claim_sum += amount
        if "전세권" in kind:
            enriched["전세권여부"] = "예"
            claim_sum += amount
        if "가등기" in kind:
            enriched["가등기여부"] = "예"

        if "청구" in kind:
            claim_sum = max(claim_sum, amount)

    if main_creditor:
        enriched["주요채권자"] = main_creditor

    existing_debt = _safe_float(enriched.get("부채총액"))
    if claim_sum > existing_debt:
        enriched["부채총액"] = str(int(claim_sum))

    return enriched


def _extract_first(pattern: str, text: str, flags: int = 0) -> str:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ""


def _korean_amount_to_number(text: str) -> str:
    """한글 단위 금액(억/만)을 정수 문자열로 변환한다."""
    src = _norm_text(text).replace(" ", "").replace(".", "")
    if not src:
        return ""

    # 숫자만 있는 경우
    only_num = re.fullmatch(r"[0-9,]+", src)
    if only_num:
        return src.replace(",", "")

    # 예: 8억1,600만 / 2억 / 9500만
    total = 0
    eok_match = re.search(r"([0-9][0-9,]*)억", src)
    man_match = re.search(r"([0-9][0-9,]*)만", src)
    chun_match = re.search(r"([0-9][0-9,]*)천", src)

    if eok_match:
        total += int(eok_match.group(1).replace(",", "")) * 100_000_000
    if man_match:
        total += int(man_match.group(1).replace(",", "")) * 10_000

    # 희소 케이스: 5천만원/7천만
    if chun_match and "만" in src and not man_match:
        total += int(chun_match.group(1).replace(",", "")) * 10_000_000

    if total > 0:
        return str(total)

    numeric = re.search(r"([0-9][0-9,]{2,})", src)
    return numeric.group(1).replace(",", "") if numeric else ""


def _extract_amount_by_labels(text: str, labels: list[str]) -> str:
    """라벨 기반으로 금액을 추출하고 숫자 문자열로 표준화한다."""
    amount_token = r"([0-9][0-9,\.\s]*억\s*(?:[0-9][0-9,\.\s]*만)?\s*(?:원)?|[0-9][0-9,\.\s]*만\s*(?:원)?|[0-9][0-9,\.\s]{4,}(?:원)?)"

    def pick_best(candidates: list[str]) -> str:
        best = ""
        best_num = 0
        for cand in candidates:
            c = str(cand or "").strip()
            if not c:
                continue
            # 비율(64%) 같은 후보 제거
            if "%" in c:
                continue
            parsed = _korean_amount_to_number(c.replace("원", ""))
            value = int(parsed) if parsed.isdigit() else 0
            if value > best_num:
                best_num = value
                best = parsed
        return best

    def fallback_digits_near_label(line: str, label: str) -> str:
        if label not in line:
            return ""
        right = line.split(label, 1)[-1]
        raw = _extract_first(r"([0-9][0-9,\.\s]{4,})", right)
        digits = re.sub(r"[^0-9]", "", raw)
        return digits if len(digits) >= 5 else ""

    for label in labels:
        line_candidates = []
        for line in text.splitlines():
            if label in line:
                line_candidates.extend(re.findall(amount_token, line))
                fallback = fallback_digits_near_label(line, label)
                if fallback:
                    line_candidates.append(fallback)

        picked_line = pick_best(line_candidates)
        if picked_line:
            return picked_line

        # 줄바꿈/공백 변형 대비 백업 검색
        nearby_pattern = rf"{label}[^\n\r]{{0,120}}"
        for segment in re.findall(nearby_pattern, text):
            segment_candidates = re.findall(amount_token, segment)
            picked_seg = pick_best(segment_candidates)
            if picked_seg:
                return picked_seg

    return ""


def _extract_case_number(text: str) -> str:
    raw = _extract_first(r"(\d{4}\s*타\s*경\s*\d{2,10})", text)
    if not raw:
        raw = _extract_first(r"사건번호\s*[:：]?\s*(\d{4}\s*타\s*경\s*\d{2,10})", text)
    return _normalize_case_number(raw)


def _extract_sale_date(text: str) -> str:
    date = _extract_first(r"(?:입찰|매각기일)\s*[:：]?\s*(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})", text)
    return date.replace("-", ".").replace("/", ".") if date else ""


def _extract_court_name(text: str) -> str:
    court = _extract_first(r"((?:서울|부산|대구|인천|광주|대전|울산|수원|의정부|춘천|청주|전주|창원|제주)[^\n\r]{0,20}지방법원(?:[^\n\r]{0,8}지원)?)", text)
    if court:
        return re.sub(r"\s+", "", court)
    return _extract_first(r"법원명\s*[:：]?\s*([^\n\r]+)", text)


def _extract_creditor_name(text: str) -> str:
    patterns = [
        r"(?:채\s*권\s*자|권\s*리\s*자)\s*[:：]?\s*([^\n\r]+)",
        r"임의경매\s*신청\s*채권자\s*[:：]?\s*([^\n\r]+)",
        r"근저당권자\s*[:：]?\s*([^\n\r]+)",
    ]
    for p in patterns:
        v = _extract_first(p, text)
        if v:
            return v.strip()
    return ""


def _get_paddle_ocr() -> Any:
    global _PADDLE_OCR_INSTANCE
    if _PADDLE_OCR_INSTANCE is not None:
        return _PADDLE_OCR_INSTANCE
    if PaddleOCR is None:
        return None
    try:
        _PADDLE_OCR_INSTANCE = PaddleOCR(use_angle_cls=True, lang="korean", show_log=False)
    except Exception:
        _PADDLE_OCR_INSTANCE = None
    return _PADDLE_OCR_INSTANCE


def _build_local_ocr_variants(image_bytes: bytes, mode: str) -> list[Image.Image]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    w, h = img.size
    min_side = min(w, h)
    if min_side < 1200:
        scale = 1200.0 / max(1, min_side)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    sharp = gray.filter(ImageFilter.SHARPEN)
    bw_soft = sharp.point(lambda p: 255 if p > 150 else 0)
    bw_hard = sharp.point(lambda p: 255 if p > 135 else 0)

    if mode == "text_first":
        variants = [sharp, bw_soft, bw_hard]

        # 긴 모바일 캡처는 세로 분할 변형을 추가해 작은 글자 판독률을 높인다.
        w, h = sharp.size
        if h >= 1500:
            strip_h = 1300
            overlap = 180
            y = 0
            strip_count = 0
            max_strip_count = 8
            while y < h:
                y2 = min(h, y + strip_h)
                variants.append(sharp.crop((0, y, w, y2)))
                variants.append(bw_soft.crop((0, y, w, y2)))
                strip_count += 1
                if strip_count >= max_strip_count:
                    break
                if y2 >= h:
                    break
                y = y2 - overlap

        return variants
    return [gray, sharp, bw_soft]


def _run_paddle_ocr_text(image_variants: list[Image.Image]) -> dict[str, Any]:
    ocr = _get_paddle_ocr()
    if ocr is None or np is None:
        return {"text": "", "confidence": 0.0, "available": False}

    best_text = ""
    best_conf = 0.0
    candidates: list[dict[str, Any]] = []

    for img in image_variants:
        arr = np.array(img.convert("RGB"))
        lines = []
        confs = []
        try:
            raw = ocr.ocr(arr, cls=True)
        except Exception:
            continue

        blocks = raw[0] if raw and isinstance(raw, list) else []
        for item in blocks or []:
            if not item or len(item) < 2:
                continue
            text_info = item[1]
            if not text_info or len(text_info) < 2:
                continue
            line_text = str(text_info[0] or "").strip()
            try:
                line_conf = float(text_info[1])
            except Exception:
                line_conf = 0.0
            if line_text:
                lines.append(line_text)
                confs.append(line_conf)

        joined = "\n".join(lines).strip()
        avg_conf = (sum(confs) / len(confs)) if confs else 0.0
        if joined:
            candidates.append({"text": joined, "confidence": avg_conf})
        if avg_conf > best_conf or (avg_conf == best_conf and len(joined) > len(best_text)):
            best_text = joined
            best_conf = avg_conf

    candidates_sorted = sorted(
        candidates,
        key=lambda x: (float(x.get("confidence", 0.0)), len(str(x.get("text") or ""))),
        reverse=True,
    )
    return {
        "text": best_text,
        "confidence": best_conf,
        "available": True,
        "candidates": candidates_sorted[:5],
    }


def _run_tesseract_ocr_text(image_variants: list[Image.Image]) -> dict[str, Any]:
    if pytesseract is None:
        return {"text": "", "confidence": 0.0, "available": False}

    best_text = ""
    best_conf = 0.0
    tess_config = "--oem 3 --psm 6"
    candidates: list[dict[str, Any]] = []

    for img in image_variants:
        try:
            text = pytesseract.image_to_string(img, lang="kor+eng", config=tess_config)
        except Exception:
            continue

        try:
            data = pytesseract.image_to_data(
                img,
                lang="kor+eng",
                config=tess_config,
                output_type=pytesseract.Output.DICT,
            )
            conf_values = [float(v) for v in data.get("conf", []) if str(v).strip() not in {"", "-1"}]
            avg_conf = (sum(conf_values) / len(conf_values) / 100.0) if conf_values else 0.0
        except Exception:
            avg_conf = 0.0

        text = str(text or "").strip()
        if text:
            candidates.append({"text": text, "confidence": avg_conf})
        if avg_conf > best_conf or (avg_conf == best_conf and len(text) > len(best_text)):
            best_text = text
            best_conf = avg_conf

    candidates_sorted = sorted(
        candidates,
        key=lambda x: (float(x.get("confidence", 0.0)), len(str(x.get("text") or ""))),
        reverse=True,
    )
    return {
        "text": best_text,
        "confidence": best_conf,
        "available": True,
        "candidates": candidates_sorted[:5],
    }


def _build_best_row_from_ocr_candidates(candidates: list[dict[str, Any]], default_columns: List[str], image_name: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for cand in candidates[:5]:
        text = str(cand.get("text") or "").strip()
        if not text:
            continue
        text_sig = str(hash(text))
        if text_sig in seen_hashes:
            continue
        seen_hashes.add(text_sig)
        rows.append(_parse_text_to_row(text, default_columns, image_name))

    if not rows:
        return _parse_text_to_row("", default_columns, image_name)

    merged_candidates = _merge_extracted_rows(rows, default_columns)
    if merged_candidates:
        return merged_candidates[0]
    return rows[0]


def _core_field_score(row: dict[str, Any]) -> int:
    keys = ["사건번호", "감정가", "최저매각가격", "부채총액", "주소", "주요채권자"]
    return sum(1 for k in keys if _is_informative_text(row.get(k)))


def _needs_tesseract_retry(paddle_row: dict[str, Any], paddle_conf: float) -> bool:
    if paddle_conf < 0.72:
        return True
    if _core_field_score(paddle_row) < 4:
        return True
    return False


def _merge_engine_rows_with_priority(paddle_row: dict[str, Any], tesseract_row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(paddle_row)

    text_priority_fields = ["사건번호", "법원명", "주소", "아파트명", "주요채권자", "권리요약", "AI_심층분석"]
    numeric_priority_fields = ["감정가", "최저매각가격", "낙찰예상가", "부채총액", "KB시세", "매각기일", "물건번호"]
    yes_no_fields = ["근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"]

    for field in text_priority_fields:
        p = merged.get(field, "")
        t = tesseract_row.get(field, "")
        if not _is_informative_text(p) and _is_informative_text(t):
            merged[field] = t

    for field in numeric_priority_fields:
        p = merged.get(field, "")
        t = tesseract_row.get(field, "")
        p_num = _safe_float(p)
        t_num = _safe_float(t)
        if t_num > p_num:
            merged[field] = t
        elif not _is_informative_text(p) and _is_informative_text(t):
            merged[field] = t

    for field in yes_no_fields:
        p = _norm_text(merged.get(field))
        t = _norm_text(tesseract_row.get(field))
        if p != "예" and t == "예":
            merged[field] = "예"
        elif not p and t:
            merged[field] = t

    return _normalize_extracted_row(merged)


def _parse_text_to_row(raw_text: str, default_columns: List[str], image_name: str) -> dict[str, Any]:
    df = parse_captured_text_to_dataframe(raw_text, default_columns)
    row = df.iloc[0].to_dict() if not df.empty else {col: "" for col in default_columns}
    row["원본파일명"] = image_name
    return _normalize_extracted_row(row)


def _process_images_with_local_hybrid(image_files: List[Any], default_columns: List[str], mode: str = "balanced") -> pd.DataFrame:
    paddle_ok = _get_paddle_ocr() is not None and np is not None
    tesseract_ok = pytesseract is not None
    if not paddle_ok and not tesseract_ok:
        raise RuntimeError(
            "❌ 로컬 OCR 엔진을 찾지 못했습니다. 'paddleocr', 'pytesseract', 'opencv-python-headless' 설치 후 다시 실행해 주세요."
        )

    rows: list[dict[str, Any]] = []

    for img_file in image_files:
        image_bytes = img_file.getvalue()
        variants = _build_local_ocr_variants(image_bytes, mode)

        paddle_res = _run_paddle_ocr_text(variants) if paddle_ok else {"text": "", "confidence": 0.0}
        paddle_row = _build_best_row_from_ocr_candidates(
            paddle_res.get("candidates", []),
            default_columns,
            img_file.name,
        )
        if _core_field_score(paddle_row) == 0:
            paddle_row = _parse_text_to_row(paddle_res.get("text", ""), default_columns, img_file.name)

        final_row = paddle_row
        tesseract_used = False

        if tesseract_ok and _needs_tesseract_retry(paddle_row, float(paddle_res.get("confidence", 0.0))):
            tesseract_res = _run_tesseract_ocr_text(variants)
            tess_row = _build_best_row_from_ocr_candidates(
                tesseract_res.get("candidates", []),
                default_columns,
                img_file.name,
            )
            if _core_field_score(tess_row) == 0:
                tess_row = _parse_text_to_row(tesseract_res.get("text", ""), default_columns, img_file.name)

            merged_row = _merge_engine_rows_with_priority(paddle_row, tess_row)
            if _core_field_score(merged_row) >= _core_field_score(paddle_row):
                final_row = merged_row
                tesseract_used = True

        auto_summary = build_structured_case_summary(final_row)
        final_row["권리요약"] = auto_summary["자동정리요약"]
        final_row["담당자메모"] = build_case_briefing(final_row)
        final_row["심사상태"] = auto_summary["정리상태"]
        final_row["AI_심층분석"] = (
            ("[로컬 OCR] PaddleOCR 1차 추출" if paddle_ok else "[로컬 OCR] Tesseract 단독 추출")
            + (" + Tesseract 저신뢰 재시도/필드보완" if paddle_ok and tesseract_used else "")
            + " 결과입니다."
        )
        rows.append(final_row)

    merged_rows = _merge_extracted_rows(rows, default_columns)
    return pd.DataFrame(merged_rows)


def parse_captured_text_to_dataframe(raw_text: str, default_columns: List[str]) -> pd.DataFrame:
    """Gemini 없이 캡처에서 복사한 텍스트를 직접 구조화한다.

    429 한도 초과 시 사용자 우회 경로로 사용한다.
    """
    text = str(raw_text or "").strip()
    row = {col: "" for col in default_columns}

    if not text:
        return pd.DataFrame([row])

    case_no = _extract_case_number(text)
    appraisal = _extract_amount_by_labels(text, ["감정가격", "감정가", "감정평가액", "감정평가금액"])
    min_price = _extract_amount_by_labels(text, ["최저가격", "최저매각가격", "최저매각가", "최저가"])
    claim = _extract_amount_by_labels(text, ["청구", "청구금액", "채권최고액", "채권액", "채권금액"])
    bid_date = _extract_sale_date(text)
    creditor = _extract_creditor_name(text)
    court_name = _extract_court_name(text)

    addr = _extract_first(r"((?:서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)[^\n\r]{6,80})", text)
    apt = _extract_first(r"\((?:[^\)]*?,)?\s*([^\)\n\r]*아파트)\)", text)

    kb_general_manwon = _extract_first(r"일반평균\s*([0-9,]+)", text)
    if not kb_general_manwon:
        kb_general_manwon = _extract_first(r"KB시세\s*[:：]?\s*([0-9,]+억(?:[0-9,]+만)?|[0-9,]+만|[0-9,]+)", text)
    if not kb_general_manwon:
        kb_general_manwon = _extract_first(r"(?:일반평균|매매가|평균시세)\s*[:：]?\s*([0-9,\.\s]+억(?:[0-9,\.\s]+만)?|[0-9,\.\s]+만|[0-9,\.\s]{5,})", text)
    kb_price = ""
    if kb_general_manwon:
        parsed_kb = _korean_amount_to_number(kb_general_manwon)
        if parsed_kb:
            # 일반평균은 만원 단위가 자주 들어오므로 숫자가 짧으면 만원으로 간주
            if parsed_kb.isdigit() and len(parsed_kb) <= 7 and "억" not in kb_general_manwon and "만" not in kb_general_manwon:
                kb_price = str(int(parsed_kb) * 10_000)
            else:
                kb_price = parsed_kb

    row["사건번호"] = case_no
    row["감정가"] = appraisal
    row["최저매각가격"] = min_price
    row["낙찰예상가"] = min_price
    row["부채총액"] = claim
    row["매각기일"] = bid_date
    row["법원명"] = court_name
    row["주소"] = addr
    row["아파트명"] = apt
    row["KB시세"] = kb_price
    row["주요채권자"] = creditor
    row["원본파일명"] = "TEXT_INPUT"

    text_compact = text.replace(" ", "")
    if "근저당" in text_compact:
        row["근저당여부"] = "예"
    if "가압류" in text_compact:
        row["가압류여부"] = "예"
    if "가처분" in text_compact:
        row["가처분여부"] = "예"
    if "압류" in text_compact and "가압류" not in text_compact:
        row["압류여부"] = "예"
    if "임차" in text_compact:
        row["임차권등기여부"] = "예"
    if "전세권" in text_compact:
        row["전세권여부"] = "예"
    if "가등기" in text_compact:
        row["가등기여부"] = "예"

    row = _normalize_extracted_row(row)
    auto_summary = build_structured_case_summary(row)
    row["권리요약"] = auto_summary["자동정리요약"]
    row["담당자메모"] = build_case_briefing(row)
    row["심사상태"] = auto_summary["정리상태"]
    row["AI_심층분석"] = "[텍스트직접분석] Gemini 호출 없이 붙여넣은 텍스트를 구조화했습니다."

    return pd.DataFrame([row])


def _group_case_key(row: dict[str, Any]) -> str:
    case_no = _normalize_case_number(row.get("사건번호"))
    if case_no and case_no not in {"판독불가", "정보없음", "AI쿼터대기", "미상"}:
        return f"case:{case_no.replace(' ', '')}"

    addr = _norm_text(row.get("주소"))
    apt = _norm_text(row.get("아파트명"))
    if addr or apt:
        return f"addr:{addr}|apt:{apt}"

    src = _norm_text(row.get("원본파일명"))
    return f"file:{src}"


def _is_informative_text(value: Any) -> bool:
    text = _norm_text(value)
    if not text:
        return False
    low = text.lower()
    placeholders = ["미상", "판독불가", "정보없음", "n/a", "unknown", "없음"]
    return all(token not in low for token in placeholders)


def _merge_extracted_rows(rows: list[dict[str, Any]], default_columns: List[str]) -> list[dict[str, Any]]:
    """여러 장 캡처에서 추출된 행을 사건 단위로 병합해 누락 필드를 보완한다."""
    if not rows:
        return []

    numeric_fields = {"감정가", "최저매각가격", "낙찰예상가", "부채총액", "KB시세"}
    yes_no_fields = {"청산가능여부", "근저당여부", "압류여부", "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부"}

    grouped: dict[str, dict[str, Any]] = {}
    sources: dict[str, list[str]] = {}
    analyses: dict[str, list[str]] = {}

    for row in rows:
        row = _normalize_extracted_row(row)
        key = _group_case_key(row)
        if key not in grouped:
            grouped[key] = {col: "" for col in default_columns}
            sources[key] = []
            analyses[key] = []

        merged = grouped[key]
        src = _norm_text(row.get("원본파일명"))
        if src and src not in sources[key]:
            sources[key].append(src)

        analysis_text = _norm_text(row.get("AI_심층분석"))
        if analysis_text and analysis_text not in analyses[key]:
            analyses[key].append(analysis_text)

        for col in default_columns:
            incoming = row.get(col, "")
            existing = merged.get(col, "")

            if col in numeric_fields:
                incoming_num = _safe_float(incoming)
                existing_num = _safe_float(existing)
                if incoming_num > existing_num:
                    merged[col] = incoming
                continue

            if col in yes_no_fields:
                if _norm_text(incoming) == "예" or _norm_text(existing) == "예":
                    merged[col] = "예"
                elif not _norm_text(existing) and _norm_text(incoming):
                    merged[col] = incoming
                continue

            incoming_info = _is_informative_text(incoming)
            existing_info = _is_informative_text(existing)

            if incoming_info and not existing_info:
                merged[col] = incoming
            elif incoming_info and existing_info and len(_norm_text(incoming)) > len(_norm_text(existing)):
                merged[col] = incoming
            elif not _norm_text(existing) and _norm_text(incoming):
                merged[col] = incoming

    merged_rows: list[dict[str, Any]] = []
    for key, merged in grouped.items():
        merged = _normalize_extracted_row(merged)
        merged["원본파일명"] = ", ".join(sources.get(key, [])[:6])
        merged["AI_심층분석"] = "\n\n".join(analyses.get(key, [])[:2])

        auto_summary = build_structured_case_summary(merged)
        merged["권리요약"] = auto_summary["자동정리요약"]
        merged["담당자메모"] = build_case_briefing(merged)
        merged["심사상태"] = auto_summary["정리상태"]
        merged_rows.append(merged)

    return merged_rows


def _process_images_with_gemini(api_key: str, image_files: List[Any], default_columns: List[str], mode: str = "balanced") -> pd.DataFrame:
    """
    최고위 전문가용: 여러 장의 이미지를 파싱하고, 무조건 1개 이상의 데이터를 반환하도록 강제합니다.
    개선사항:
    - 상세한 에러 로깅
    - 더 명확한 AI 프롬프트
    - 안정적인 fallback 처리
    """
    if not api_key:
        raise ValueError("❌ Gemini API 키가 필요합니다. https://makersuite.google.com/app/apikey 에서 발급받으세요.")
    if genai is None:
        raise RuntimeError("❌ google-generativeai 패키지가 설치되지 않았습니다. requirements.txt 설치 후 다시 실행해 주세요.")
    
    print(f"[Vision AI] API 키 설정 중... (키 길이: {len(api_key)}자)")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')
    print(f"[Vision AI] Gemini 1.5 Pro 모델 로드 완료")

    prompt = """
    당신은 한국 법원 경매 및 NPL 투자 심사를 수행하는 최상위 실무형 전문가입니다.
    다음 이미지에서 경매 물건의 핵심 정보를 정확하고 빠르게 추출하여 반드시 JSON 배열로 반환하십시오.

    ⚠️ 필수 규칙:
    1. 절대 빈 배열([])을 반환하지 마십시오.
    2. 이미지가 흐리거나 일부 정보가 누락되더라도, 보이는 항목은 최대한 정확히 추출하십시오.
    3. 모르면 "미상" 또는 "0" 또는 ""로 채우되, 반드시 객체를 생성하십시오.
    4. 여러 이미지가 동일 물건을 반복해도 각각 별개 객체로 처리하십시오.
    5. 숫자는 쉼표 없이 작성하십시오. 예: 500000000.
    6. 값이 불명확하면 추정하되, 추정 근거를 AI_심층분석에 포함하십시오.

    [우선 추출 대상]
    - 원본파일명
    - 사건번호
    - 매각기일
    - 법원명
    - 물건번호
    - 주소
    - 아파트명
    - 감정가
    - 최저매각가격
    - 낙찰예상가
    - 부채총액
    - KB시세
    - 주요채권자
    - 청산가능여부
    - 근저당여부
    - 압류여부
    - 가압류여부
    - 가처분여부
    - 임차권등기여부
    - 전세권여부
    - 가등기여부

    [전문가 심층 분석 형식]
    - AI_심층분석: 3~4문장으로 작성하되, 다음 요소를 포함하십시오.
      1) 시세 대비 부채비율(LTV) 또는 낙찰가 대비 부담 수준
      2) 권리상 하자와 명도 리스크
      3) 실무상 청산 가능성 또는 협의 가능성
      4) 채권자/법원 관점에서의 핵심 리스크

    [출력 형식]
    반드시 아래 형식의 JSON 배열만 반환하십시오.
    [
      {
        "원본파일명": "",
        "사건번호": "",
        "매각기일": "",
        "법원명": "",
        "물건번호": "",
        "주소": "",
        "아파트명": "",
        "감정가": "",
        "최저매각가격": "",
        "낙찰예상가": "",
        "부채총액": "",
        "KB시세": "",
        "주요채권자": "",
        "청산가능여부": "",
        "근저당여부": "",
        "압류여부": "",
        "가압류여부": "",
        "가처분여부": "",
        "임차권등기여부": "",
        "전세권여부": "",
        "가등기여부": "",
                "AI_심층분석": "",
                "권리항목목록": [
                    {
                        "접수": "",
                        "종류": "",
                        "권리자": "",
                        "금액": "",
                        "소멸": ""
                    }
                ]
      }
    ]
    """

    if mode == "text_first":
        prompt += """

    [텍스트 우선 OCR 모드 규칙]
    - 사진, 지도, 아이콘, 광고 요소는 무시하고 표/문장 텍스트만 읽습니다.
    - 같은 항목이 반복되면 숫자/고유명사(사건번호, 금액, 채권자, 주소)가 더 선명한 값을 선택합니다.
    - 표의 열 제목(접수순서/종류/권리자/소멸 등)을 기준으로 항목을 정렬해 해석합니다.
    """

    print(f"[Vision AI] 이미지 파일 로드 중... (총 {len(image_files)}개, mode={mode})")

    extracted_rows: list[dict[str, Any]] = []
    attempt_delays = [0, 10, 65]

    try:
        for idx, img_file in enumerate(image_files):
            image_bytes = img_file.getvalue()
            file_size = len(image_bytes) / 1024
            print(f"[Vision AI] 이미지 {idx+1}/{len(image_files)}: {img_file.name} ({file_size:.1f}KB)")

            quality = assess_image_quality(image_bytes)
            print(f"[Vision AI] 이미지 {idx+1} 품질 점수: {quality['score']} / 캡처 보정 필요: {quality['needs_recapture']}")

            # 정확도와 안정성을 위해 이미지 단위로 분리 호출한다.
            request_payload = [prompt]
            request_payload.extend(_build_image_parts_for_mode(img_file.name, image_bytes, mode))
            request_payload.append(
                (
                    f"\n\n[이미지 파일명: {img_file.name}]\n"
                    f"이 이미지만 분석하고 '원본파일명' 필드에 '{img_file.name}'을 반드시 포함하십시오.\n"
                )
            )

            response_text = ""
            for attempt, delay in enumerate(attempt_delays, start=1):
                if delay > 0:
                    print(f"[Vision AI] 호출 제한 회피를 위해 {delay}초 대기 후 재시도합니다... ({attempt}/{len(attempt_delays)})")
                    time.sleep(delay)

                try:
                    response = model.generate_content(request_payload)
                    response_text = str(getattr(response, "text", "") or "").strip()
                    if not response_text:
                        raise ValueError("AI 응답이 비어 있습니다.")
                    print(f"[Vision AI] ✓ API 응답 수신 완료 (응답 길이: {len(response_text)}자)")
                    break
                except Exception as api_error:
                    if _is_rate_limited_error(api_error):
                        print(f"[Vision AI] ⚠️ Rate limit 감지: {api_error}")
                        if attempt == len(attempt_delays):
                            return _build_quota_fallback_dataframe(
                                image_files,
                                default_columns,
                                "[보류] Gemini API 분당 호출 한도(429 RATE_LIMIT_EXCEEDED)로 자동 판독이 지연되었습니다.",
                            )
                        continue
                    raise

            result_text = _extract_json_array_text(response_text)
            print(f"[Vision AI] 클린업된 JSON 텍스트:")
            print(result_text[:500])

            try:
                parsed_data = json.loads(result_text)
                extracted_count = len(parsed_data) if isinstance(parsed_data, list) else 1
                print(f"[Vision AI] ✓ JSON 파싱 성공! 추출된 객체 수: {extracted_count}")
            except json.JSONDecodeError as je:
                print(f"[Vision AI] ✗ JSON 파싱 실패: {je}")
                print(f"[Vision AI] 원본 응답: {response_text[:1000]}")
                parsed_data = [{
                    "사건번호": "판독불가",
                    "원본파일명": img_file.name,
                    "AI_심층분석": f"[오류] AI 응답을 JSON으로 변환하는 데 실패했습니다. 원본 응답: {response_text[:200]}...",
                }]

            rows = _to_rows(parsed_data, img_file.name, default_columns)
            extracted_rows.extend(rows)
            print(f"[Vision AI]   - 이미지 완료: {img_file.name}, 생성 행 수={len(rows)}")

        merged_rows = _merge_extracted_rows(extracted_rows, default_columns)
        result_df = pd.DataFrame(merged_rows)
        print(f"[Vision AI] ✅ 최종 DataFrame 생성 완료: {len(result_df)}행 x {len(result_df.columns)}열 (원본행 {len(extracted_rows)}건 병합)")
        return result_df
        
    except Exception as e:
        print(f"[Vision AI] ❌ 치명적 오류 발생: {type(e).__name__}: {e}")
        import traceback
        print(f"[Vision AI] 상세 스택:")
        traceback.print_exc()
        short_reason = str(e)
        if len(short_reason) > 280:
            short_reason = short_reason[:280] + "..."
        raise Exception(
            f"❌ AI 심층 구조화 파싱 실패: {short_reason}\n\n가능한 원인:\n"
            "1. API 키가 만료되었거나 잘못됨\n"
            "2. 네트워크 연결 문제\n"
            "3. 이미지 파일이 손상됨\n"
            "4. API 할당량 초과"
        )


def process_images_to_dataframe(
    api_key: str,
    image_files: List[Any],
    default_columns: List[str],
    mode: str = "balanced",
    engine: str = "auto",
) -> pd.DataFrame:
    """이미지 OCR 파이프라인 진입점.

    engine:
    - auto: API 키와 Gemini 패키지가 있으면 Gemini, 없으면 로컬 하이브리드
    - gemini: Gemini 강제
    - local_hybrid: PaddleOCR + Tesseract 강제
    """
    normalized_engine = str(engine or "auto").strip().lower()
    if normalized_engine not in {"auto", "gemini", "local_hybrid"}:
        normalized_engine = "auto"

    if normalized_engine == "local_hybrid":
        return _process_images_with_local_hybrid(image_files, default_columns, mode=mode)

    if normalized_engine == "gemini":
        return _process_images_with_gemini(api_key, image_files, default_columns, mode=mode)

    can_use_gemini = bool(str(api_key or "").strip()) and genai is not None
    if can_use_gemini:
        return _process_images_with_gemini(api_key, image_files, default_columns, mode=mode)
    return _process_images_with_local_hybrid(image_files, default_columns, mode=mode)
