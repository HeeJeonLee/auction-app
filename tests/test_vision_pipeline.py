import warnings
from io import BytesIO
from PIL import Image

from vision_extractor import (
    build_structured_case_summary,
    build_case_briefing,
    assess_image_quality,
    build_recapture_guidance,
    detect_missing_fields,
    process_images_to_dataframe,
    parse_captured_text_to_dataframe,
    _merge_extracted_rows,
    _build_image_parts_for_mode,
    _merge_engine_rows_with_priority,
    _needs_tesseract_retry,
    _normalize_extracted_row,
    _to_rows,
)


def test_build_structured_case_summary_produces_readable_output():
    row = {
        "사건번호": "2026001",
        "법원명": "수원지법",
        "아파트명": "한진아파트",
        "주소": "경기도 수원시",
        "감정가": "500000000",
        "부채총액": "400000000",
        "KB시세": "1억원",
        "주요채권자": "수협",
        "근저당여부": "예",
    }

    result = build_structured_case_summary(row)

    assert result["정리상태"] in {"완료", "보완필요"}
    assert result["완성도"] >= 0
    assert "한진아파트" in result["자동정리요약"] or "수원" in result["자동정리요약"]


def test_build_case_briefing_contains_strategy_points():
    row = {
        "사건번호": "2026001",
        "아파트명": "한진아파트",
        "부채총액": "800000000",
        "KB시세": "1억원",
        "주요채권자": "수협",
        "근저당여부": "예",
        "압류여부": "아니오",
    }

    brief = build_case_briefing(row)

    assert "권리" in brief or "협상" in brief
    assert "수협" in brief or "채권자" in brief


def test_assess_image_quality_and_guidance():
    img = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    quality = assess_image_quality(buffer.getvalue())
    guidance = build_recapture_guidance(quality)

    assert quality["score"] >= 0
    assert "profile" in quality
    assert "recommended_min_score" in quality
    assert isinstance(guidance, str)
    assert len(guidance) > 0


def test_detect_missing_fields_reports_essential_gaps():
    row = {"사건번호": "2026001", "아파트명": "한진아파트"}
    missing = detect_missing_fields(row)

    assert "부채총액" in missing
    assert "주요채권자" in missing


def test_assess_image_quality_does_not_emit_deprecation_warning():
    img = Image.new("RGB", (120, 120), color=(255, 255, 255))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assess_image_quality(buffer.getvalue())

    assert not any("getdata" in str(w.message) for w in caught)


def test_assess_image_quality_identifies_mobile_long_profile():
    img = Image.new("RGB", (800, 2200), color=(245, 245, 245))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    quality = assess_image_quality(buffer.getvalue())
    assert quality["profile"] == "mobile_long"
    assert quality["recommended_min_score"] == 60


class _DummyUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def test_process_images_to_dataframe_returns_quota_hold_rows_on_429(monkeypatch):
    class _DummyModel:
        def generate_content(self, _payload):
            raise Exception("429 RATE_LIMIT_EXCEEDED quota exceeded")

    class _DummyGenAI:
        def configure(self, **_kwargs):
            return None

        def GenerativeModel(self, _name):
            return _DummyModel()

    monkeypatch.setattr("vision_extractor.genai", _DummyGenAI())
    monkeypatch.setattr("vision_extractor.time.sleep", lambda _sec: None)

    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    file_obj = _DummyUpload("sample.png", buffer.getvalue())

    default_columns = ["원본파일명", "사건번호", "권리요약", "AI_심층분석", "담당자메모", "심사상태"]
    df = process_images_to_dataframe("dummy_key", [file_obj], default_columns)

    assert len(df) == 1
    assert df.iloc[0]["사건번호"] == "AI쿼터대기"
    assert "보류" in str(df.iloc[0]["AI_심층분석"])


def test_merge_extracted_rows_complements_fields_for_same_case():
    default_columns = [
        "원본파일명", "사건번호", "주소", "아파트명", "감정가", "낙찰예상가", "KB시세",
        "부채총액", "주요채권자", "근저당여부", "압류여부", "AI_심층분석", "권리요약", "담당자메모", "심사상태",
    ]

    rows = [
        {
            "원본파일명": "case_main.png",
            "사건번호": "2024타경2979",
            "주소": "서울 강동구 천호동 52-17",
            "아파트명": "태천해오름",
            "감정가": "796000000",
            "낙찰예상가": "509440000",
            "AI_심층분석": "메인 요약",
        },
        {
            "원본파일명": "kb_price.png",
            "사건번호": "2024타경2979",
            "KB시세": "816000000",
            "부채총액": "202774869",
            "주요채권자": "유더블유제십오차유동화전문유한회사",
            "근저당여부": "예",
            "압류여부": "예",
            "AI_심층분석": "시세/채권 정보",
        },
    ]

    merged = _merge_extracted_rows(rows, default_columns)

    assert len(merged) == 1
    merged_row = merged[0]
    assert merged_row["사건번호"] == "2024타경2979"
    assert str(merged_row["KB시세"]).strip() != ""
    assert str(merged_row["주요채권자"]).strip() != ""
    assert merged_row["근저당여부"] == "예"
    assert merged_row["압류여부"] == "예"


def test_build_image_parts_for_text_first_returns_segmented_parts():
    img = Image.new("RGB", (900, 2200), color=(255, 255, 255))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    parts = _build_image_parts_for_mode("long_capture.png", buffer.getvalue(), "text_first")

    assert len(parts) >= 2
    image_dict_count = sum(1 for p in parts if isinstance(p, dict) and "data" in p)
    assert image_dict_count >= 2


def test_normalize_extracted_row_cleans_core_fields():
    raw = {
        "사건번호": " 2024 타경 2979 ",
        "부채총액": "청구:202,774,869",
        "KB시세": " 8억 1,600만 원 ",
        "근저당여부": "있음",
        "압류여부": "없음",
        "주요채권자": "  유더블유제십오차유동화전문유한회사  ",
    }

    row = _normalize_extracted_row(raw)

    assert row["사건번호"] == "2024타경2979"
    assert row["부채총액"] == "202774869"
    assert "8억" in row["KB시세"]
    assert row["근저당여부"] == "예"
    assert row["압류여부"] == "아니오"
    assert row["주요채권자"] == "유더블유제십오차유동화전문유한회사"


def test_registry_entries_enrich_flags_and_debt():
    default_columns = [
        "원본파일명", "사건번호", "부채총액", "주요채권자", "근저당여부", "압류여부", "가압류여부",
        "가처분여부", "임차권등기여부", "전세권여부", "가등기여부", "AI_심층분석", "권리요약", "담당자메모", "심사상태",
    ]

    parsed = [{
        "원본파일명": "registry.png",
        "사건번호": "2024타경2979",
        "권리항목목록": [
            {"접수": "2002.09.09", "종류": "근저당권설정", "권리자": "우리은행", "금액": "240,000,000", "소멸": "소멸"},
            {"접수": "2023.11.16", "종류": "압류", "권리자": "국민건강보험공단", "금액": "", "소멸": "소멸"},
            {"접수": "2024.10.10", "종류": "임의경매 청구", "권리자": "유더블유제십오차유동화전문유한회사", "금액": "202,774,869", "소멸": "소멸"},
        ],
    }]

    rows = _to_rows(parsed, "registry.png", default_columns)
    assert len(rows) == 1
    row = rows[0]
    assert row["근저당여부"] == "예"
    assert row["압류여부"] == "예"
    assert "유더블유" in row["주요채권자"] or "우리은행" in row["주요채권자"]
    assert int(float(str(row["부채총액"] or "0"))) >= 202774869


def test_parse_captured_text_to_dataframe_extracts_core_fields():
    text = """
    경매 2024타경2979
    서울 강동구 천호동 52-17 (천호동,태천해오름아파트)
    감정가격 796,000,000
    최저가격 (64%) 509,440,000
    청구 202,774,869
    채권자 유더블유제십오차유동화전문유한회사
    근저당권설정 240,000,000
    압류 국민건강보험공단
    """

    default_columns = [
        "원본파일명", "사건번호", "주소", "아파트명", "감정가", "최저매각가격", "낙찰예상가",
        "부채총액", "주요채권자", "근저당여부", "압류여부", "권리요약", "담당자메모", "심사상태", "AI_심층분석"
    ]

    df = parse_captured_text_to_dataframe(text, default_columns)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["사건번호"] == "2024타경2979"
    assert str(row["감정가"]) == "796000000"
    assert str(row["최저매각가격"]) == "509440000"
    assert str(row["부채총액"]) == "202774869"
    assert "유더블유" in str(row["주요채권자"])
    assert row["근저당여부"] == "예"
    assert row["압류여부"] == "예"


def test_needs_tesseract_retry_when_confidence_or_fields_are_low():
    low_conf_row = {
        "사건번호": "2024타경2979",
        "감정가": "",
        "최저매각가격": "",
        "부채총액": "",
        "주소": "",
        "주요채권자": "",
    }
    assert _needs_tesseract_retry(low_conf_row, 0.60) is True
    assert _needs_tesseract_retry(low_conf_row, 0.90) is True

    enough_fields_row = {
        "사건번호": "2024타경2979",
        "감정가": "796000000",
        "최저매각가격": "509440000",
        "부채총액": "202774869",
        "주소": "서울 강동구 천호동 52-17",
        "주요채권자": "유더블유제십오차유동화전문유한회사",
    }
    assert _needs_tesseract_retry(enough_fields_row, 0.85) is False


def test_merge_engine_rows_with_priority_prefers_numeric_and_yes_fields():
    paddle_row = {
        "사건번호": "2024타경2979",
        "주소": "서울 강동구 천호동",
        "아파트명": "태천해오름아파트",
        "감정가": "796000000",
        "최저매각가격": "",
        "부채총액": "100000000",
        "주요채권자": "",
        "근저당여부": "아니오",
    }
    tesseract_row = {
        "사건번호": "2024타경2979",
        "최저매각가격": "509440000",
        "부채총액": "202774869",
        "주요채권자": "유더블유제십오차유동화전문유한회사",
        "근저당여부": "예",
    }

    merged = _merge_engine_rows_with_priority(paddle_row, tesseract_row)
    assert merged["최저매각가격"] == "509440000"
    assert merged["부채총액"] == "202774869"
    assert "유더블유" in merged["주요채권자"]
    assert merged["근저당여부"] == "예"


def test_parse_captured_text_handles_korean_amount_units_and_date_formats():
    text = """
    사건번호: 2024 타 경 2979
    매각기일 2026-09-15
    감정가 8억1,600만 원
    최저매각가격 (64%) 5억940만 원
    채권최고액 2억 2774만 원
    채권자 우리은행
    KB시세: 8억2,000만
    """

    default_columns = [
        "원본파일명", "사건번호", "매각기일", "감정가", "최저매각가격", "낙찰예상가",
        "부채총액", "KB시세", "주요채권자", "권리요약", "담당자메모", "심사상태", "AI_심층분석"
    ]

    df = parse_captured_text_to_dataframe(text, default_columns)
    row = df.iloc[0]

    assert row["사건번호"] == "2024타경2979"
    assert row["매각기일"] == "2026.09.15"
    assert str(row["감정가"]) == "816000000"
    assert str(row["최저매각가격"]) == "509400000"
    assert str(row["부채총액"]) == "227740000"
    assert str(row["KB시세"]) == "820000000"
    assert "우리은행" in str(row["주요채권자"])
