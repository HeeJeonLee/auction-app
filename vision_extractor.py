import os
import json
import io
import time
import re
import warnings
from typing import List, Any

import pandas as pd
from PIL import Image

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    try:
        import google.generativeai as genai
    except Exception:  # pragma: no cover - 환경에 패키지가 없을 수 있음
        genai = None

from analysis import _safe_float, get_creditor_analysis_guidance, structure_rights_analysis


def assess_image_quality(image_bytes: bytes) -> dict[str, Any]:
    """간단한 이미지 품질 지표를 계산해 재촬영 여부를 판단한다."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        gray = img.resize((200, 200))
        pixels = list(gray.get_flattened_data())
        mean_brightness = sum(pixels) / len(pixels) / 255.0
        variance = sum((p - mean_brightness) ** 2 for p in pixels) / len(pixels)
        edge_score = 0.0
        for i in range(1, gray.width - 1):
            for j in range(1, gray.height - 1):
                diff = abs(gray.getpixel((i, j)) - gray.getpixel((i - 1, j))) + abs(gray.getpixel((i, j)) - gray.getpixel((i, j - 1)))
                edge_score += diff
        edge_score /= (gray.width * gray.height * 255 * 2)

        score = 70
        if mean_brightness < 0.3:
            score -= 20
        elif mean_brightness > 0.85:
            score -= 10
        if variance < 0.02:
            score -= 15
        if edge_score < 0.05:
            score -= 10

        score = max(0, min(100, score))
        return {
            "score": int(score),
            "brightness": round(mean_brightness, 3),
            "variance": round(variance, 3),
            "edge_score": round(edge_score, 3),
            "needs_recapture": score < 65,
        }
    except Exception:
        return {"score": 50, "brightness": 0.5, "variance": 0.0, "edge_score": 0.0, "needs_recapture": True}


def build_recapture_guidance(quality: dict[str, Any]) -> str:
    if quality.get("needs_recapture"):
        return "캡처 보정 권장: 문서가 너무 어둡거나 흐릿하거나 잘려 보이면, 화면을 더 선명하게 보이도록 캡처를 다시 업로드해 주세요."
    return "품질 양호: OCR 및 자동 정리 단계로 바로 진행해도 좋습니다."


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
        else:
            row["원본파일명"] = image_name
            row["사건번호"] = "판독불가"
            row["AI_심층분석"] = "[오류] AI 결과 형식이 비정상이라 기본 행으로 대체되었습니다."

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
        auto_summary = build_structured_case_summary(row)
        row["권리요약"] = auto_summary["자동정리요약"]
        row["담당자메모"] = build_case_briefing(row)
        row["심사상태"] = auto_summary["정리상태"]
        rows.append(row)

    return rows


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _group_case_key(row: dict[str, Any]) -> str:
    case_no = _norm_text(row.get("사건번호"))
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
        merged["원본파일명"] = ", ".join(sources.get(key, [])[:6])
        merged["AI_심층분석"] = "\n\n".join(analyses.get(key, [])[:2])

        auto_summary = build_structured_case_summary(merged)
        merged["권리요약"] = auto_summary["자동정리요약"]
        merged["담당자메모"] = build_case_briefing(merged)
        merged["심사상태"] = auto_summary["정리상태"]
        merged_rows.append(merged)

    return merged_rows


def process_images_to_dataframe(api_key: str, image_files: List[Any], default_columns: List[str]) -> pd.DataFrame:
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
        "AI_심층분석": ""
      }
    ]
    """

    print(f"[Vision AI] 이미지 파일 로드 중... (총 {len(image_files)}개)")

    extracted_rows: list[dict[str, Any]] = []
    attempt_delays = [0, 10, 65]

    try:
        for idx, img_file in enumerate(image_files):
            ext = img_file.name.lower()
            mime_type = "image/jpeg" if ext.endswith(("jpg", "jpeg")) else "image/png"
            image_bytes = img_file.getvalue()
            file_size = len(image_bytes) / 1024
            print(f"[Vision AI] 이미지 {idx+1}/{len(image_files)}: {img_file.name} ({file_size:.1f}KB, {mime_type})")

            quality = assess_image_quality(image_bytes)
            print(f"[Vision AI] 이미지 {idx+1} 품질 점수: {quality['score']} / 캡처 보정 필요: {quality['needs_recapture']}")

            # 정확도와 안정성을 위해 이미지 단위로 분리 호출한다.
            request_payload = [
                prompt,
                {
                    "mime_type": mime_type,
                    "data": image_bytes,
                },
                (
                    f"\n\n[이미지 파일명: {img_file.name}]\n"
                    f"이 이미지만 분석하고 '원본파일명' 필드에 '{img_file.name}'을 반드시 포함하십시오.\n"
                ),
            ]

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
