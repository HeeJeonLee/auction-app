import warnings
from io import BytesIO
from PIL import Image

from vision_extractor import (
    build_structured_case_summary,
    build_case_briefing,
    assess_image_quality,
    build_recapture_guidance,
    detect_missing_fields,
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
