import os
import time
import hashlib
import zipfile
import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from streamlit_paste_button import paste_image_button
except Exception:  # pragma: no cover - optional dependency
    paste_image_button = None

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

from report_generator import generate_pptx_bytes, generate_pdf_bytes

from analysis import (
    calculate_candidate_score, classify_grade, recommend_lender, 
    build_rights_summary, suggest_candidate_flag, build_owner_pitch, 
    build_visit_advice, build_phone_pitch, build_visit_pitch,
    passes_market_filters, needs_registry_verification, _safe_float,
    get_creditor_advice, evaluate_case_policy, get_policy_reference,
    get_creditor_analysis_guidance
)
from manual_rule_engine import evaluate_manual_rules, get_rulepack_meta
from vision_extractor import (
    process_images_to_dataframe,
    parse_captured_text_to_dataframe,
    build_structured_case_summary,
    build_case_briefing,
    assess_image_quality,
    build_recapture_guidance,
    summarize_extraction_quality,
)

st.set_page_config(
    page_title="Auctiscope | Case Analysis & Briefing Platform", 
    page_icon="🏢", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# ==================== 고급 CSS 스타일링 ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&family=Inter:wght@300;400;600;700;900&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', 'Inter', sans-serif;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        color: #1a1a2e;
    }
    
    /* 헤더 */
    .main-header {
        font-size: 42px;
        font-weight: 900;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 20px 0;
        margin-bottom: 10px;
    }
    
    .sub-header {
        text-align: center;
        font-size: 16px;
        color: #64748b;
        margin-bottom: 40px;
        font-weight: 500;
    }
    
    /* 섹션 타이틀 */
    .section-title {
        font-size: 32px;
        font-weight: 900;
        color: #1e293b;
        margin: 60px 0 30px 0;
        padding: 20px 30px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.08);
        border-left: 8px solid #667eea;
    }

    /* KPI 메트릭 박스 */
    .metric-box {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        padding: 30px;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        border-top: 6px solid #3b82f6;
        text-align: center;
        margin-bottom: 25px;
        transition: transform 0.3s ease;
    }
    .metric-box:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 48px rgba(0,0,0,0.12);
    }
    .metric-value { 
        font-size: 48px; 
        font-weight: 900; 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 15px 0; 
    }
    .metric-title { 
        font-size: 16px; 
        font-weight: 700; 
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 적격 카드 - 대폭 강화 */
    .card-passed { 
        background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%);
        padding: 40px; 
        border-radius: 20px; 
        margin-bottom: 30px; 
        border: 2px solid #86efac;
        border-left: 12px solid #22c55e;
        box-shadow: 0 12px 48px rgba(34, 197, 94, 0.15);
        position: relative;
        overflow: hidden;
    }
    .card-passed::before {
        content: "✓ APPROVED";
        position: absolute;
        top: 15px;
        right: 20px;
        background: #22c55e;
        color: white;
        padding: 8px 20px;
        border-radius: 20px;
        font-weight: 900;
        font-size: 12px;
        letter-spacing: 2px;
    }
    
    /* 부적격 카드 - 대폭 강화 */
    .card-failed { 
        background: linear-gradient(135deg, #ffffff 0%, #fef2f2 100%);
        padding: 40px; 
        border-radius: 20px; 
        margin-bottom: 30px; 
        border: 2px solid #fca5a5;
        border-left: 12px solid #ef4444;
        box-shadow: 0 12px 48px rgba(239, 68, 68, 0.15);
        position: relative;
        overflow: hidden;
    }
    .card-failed::before {
        content: "✗ REJECTED";
        position: absolute;
        top: 15px;
        right: 20px;
        background: #ef4444;
        color: white;
        padding: 8px 20px;
        border-radius: 20px;
        font-weight: 900;
        font-size: 12px;
        letter-spacing: 2px;
    }
    
    /* AI 분석 박스 */
    .expert-analysis-box {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border-left: 6px solid #f59e0b;
        border-radius: 12px;
        padding: 25px;
        margin-top: 25px;
        font-size: 16px;
        line-height: 1.8;
        color: #78350f;
        box-shadow: 0 4px 16px rgba(245, 158, 11, 0.2);
    }

    /* 정보 라벨 */
    .info-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 20px;
        margin: 25px 0;
    }
    .info-item {
        background: #f8fafc;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
    }
    .info-label { 
        font-size: 13px; 
        color: #64748b; 
        margin-bottom: 8px;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 1px;
    }
    .info-data { 
        font-size: 20px; 
        font-weight: 700; 
        color: #1e293b; 
    }

    /* 배지 */
    .badge-approved { 
        background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
        color: white;
        padding: 10px 20px;
        border-radius: 30px;
        font-size: 15px;
        font-weight: 900;
        box-shadow: 0 4px 16px rgba(34, 197, 94, 0.3);
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .badge-rejected { 
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        color: white;
        padding: 10px 20px;
        border-radius: 30px;
        font-size: 15px;
        font-weight: 900;
        box-shadow: 0 4px 16px rgba(239, 68, 68, 0.3);
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 다운로드 버튼 */
    .stDownloadButton>button { 
        width: 100%;
        border-radius: 12px;
        font-weight: 900;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        height: 60px;
        font-size: 18px;
        box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
        transition: all 0.3s ease;
    }
    .stDownloadButton>button:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 36px rgba(102, 126, 234, 0.5);
    }
    
    /* 구분선 */
    .divider {
        height: 3px;
        background: linear-gradient(90deg, transparent, #667eea, transparent);
        margin: 40px 0;
        border-radius: 2px;
    }
    
    /* 경고 박스 */
    .warning-box {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        border: 2px solid #fbbf24;
        border-radius: 16px;
        padding: 25px;
        margin: 20px 0;
        box-shadow: 0 4px 16px rgba(251, 191, 36, 0.2);
    }
    
    /* 대부업체 카드 */
    .lender-card {
        background: white;
        border-radius: 16px;
        padding: 30px;
        margin: 20px 0;
        border-left: 6px solid #3b82f6;
        box-shadow: 0 4px 24px rgba(0,0,0,0.06);
    }
    .lender-name {
        font-size: 24px;
        font-weight: 900;
        color: #1e293b;
        margin-bottom: 15px;
    }
    .lender-contact {
        font-size: 16px;
        color: #64748b;
        margin: 8px 0;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 헤더 ====================
st.markdown("<div class='main-header'>🏢 Auctiscope</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>PC/모바일 캡처 업로드만으로 권리분석, 사건 판단, 대응 브리핑까지 이어지는 실무 보조 플랫폼</div>", unsafe_allow_html=True)
st.info("⚠️ 이 도구는 최종 법률 판단을 대신하지 않으며, 사건 정리·권리 리스크 구조화·실무 브리핑 지원을 위한 보조 도구입니다.")

# ==================== 기본 설정 ====================
DEFAULT_COLUMNS = [
    "원본파일명", "사건번호", "매각기일", "잔여일수", "법원명", "물건번호", "주소", "아파트명", "감정가", "최저매각가격", "낙찰예상가",
    "부채총액", "청산가능여부", "권리요약", "분석점수", "분석등급", "제안포인트", "담당자메모",
    "KB시세", "주요채권자", "심사상태", "추정LTV", "AI_심층분석", "등기부열람여부", "근저당여부", "압류여부", "가처분여부",
    "규칙버전", "규칙점수", "규칙판정", "규칙근거", "취하스크립트"
]

# Session State 초기화
if "df" not in st.session_state: 
    st.session_state.df = pd.DataFrame(columns=DEFAULT_COLUMNS)
if "uploaded_images" not in st.session_state: 
    st.session_state.uploaded_images = []
if "processing_log" not in st.session_state:
    st.session_state.processing_log = []
if "clipboard_images" not in st.session_state:
    st.session_state.clipboard_images = []
if "clipboard_hashes" not in st.session_state:
    st.session_state.clipboard_hashes = set()


class ClipboardImageUpload:
    """file_uploader 객체와 유사한 최소 인터페이스를 제공한다."""

    def __init__(self, image_bytes: bytes, name: str):
        self._image_bytes = image_bytes
        self.name = name
        self.type = "image/png"

    def getvalue(self) -> bytes:
        return self._image_bytes


class InMemoryImageUpload:
    """ZIP 해제 이미지 등 메모리 기반 이미지를 uploader 형식으로 맞춘다."""

    def __init__(self, image_bytes: bytes, name: str, mime_type: str = "image/png"):
        self._image_bytes = image_bytes
        self.name = name
        self.type = mime_type

    def getvalue(self) -> bytes:
        return self._image_bytes


def build_clipboard_upload(paste_result, index_hint: int):
    """클립보드 컴포넌트 결과를 업로드 객체로 변환한다."""
    if paste_result is None:
        return None

    image_data = paste_result
    if isinstance(paste_result, dict):
        image_data = (
            paste_result.get("image_data")
            or paste_result.get("image")
            or paste_result.get("data")
        )

    image_bytes = None
    if isinstance(image_data, (bytes, bytearray)):
        image_bytes = bytes(image_data)
    elif hasattr(image_data, "save"):
        buffer = BytesIO()
        image_data.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

    if not image_bytes:
        return None

    image_hash = hashlib.sha1(image_bytes).hexdigest()
    if image_hash in st.session_state.clipboard_hashes:
        return None

    st.session_state.clipboard_hashes.add(image_hash)
    file_name = f"clipboard_capture_{index_hint:03d}.png"
    return ClipboardImageUpload(image_bytes=image_bytes, name=file_name)


def is_image_upload(file_obj) -> bool:
    """업로드 객체의 MIME/확장자를 함께 확인해 이미지 여부를 안전하게 판별한다."""
    mime_type = str(getattr(file_obj, "type", "") or "").lower()
    file_name = str(getattr(file_obj, "name", "") or "").lower()
    if mime_type.startswith("image/"):
        return True
    return file_name.endswith((".png", ".jpg", ".jpeg", ".webp"))


def extract_images_from_zip(zip_file_obj, max_images: int = 300) -> tuple[list[InMemoryImageUpload], list[str]]:
    """ZIP 업로드에서 이미지 파일만 추출한다."""
    extracted: list[InMemoryImageUpload] = []
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(BytesIO(zip_file_obj.getvalue())) as zf:
            for member in zf.infolist():
                name = str(member.filename or "")
                lower_name = name.lower()
                if member.is_dir():
                    continue
                if not lower_name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    continue
                if len(extracted) >= max_images:
                    warnings.append(f"ZIP 이미지가 {max_images}장을 넘어 초과분은 건너뜁니다: {zip_file_obj.name}")
                    break

                raw = zf.read(member)
                if not raw:
                    continue
                mime = "image/jpeg" if lower_name.endswith((".jpg", ".jpeg")) else "image/png"
                safe_name = Path(name).name or f"zip_image_{len(extracted)+1:03d}.png"
                extracted.append(InMemoryImageUpload(raw, safe_name, mime_type=mime))
    except Exception as zip_error:
        warnings.append(f"ZIP 해제 실패: {getattr(zip_file_obj, 'name', 'unknown')} ({type(zip_error).__name__})")

    return extracted, warnings

def resolve_api_key() -> str:
    """환경변수, .env, Streamlit 시크릿, 세션 입력 순으로 API 키를 해석한다."""
    current = str(st.session_state.get("api_key") or "").strip()
    if current:
        return current

    if load_dotenv is not None:
        load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)

    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            return env_value

    try:
        return str(st.secrets.get("GEMINI_API_KEY", "") or "").strip()
    except Exception:
        return ""


@st.cache_data(show_spinner=False)
def read_utf8_text_file(path_value: str, mtime: float = 0.0) -> str:
    _ = mtime
    path_obj = Path(path_value)
    if not path_obj.exists():
        return ""
    return path_obj.read_text(encoding="utf-8")


@st.cache_data(show_spinner=False)
def build_manual_zip_bundle(
    manual_name: str,
    manual_text: str,
    process_name: str,
    process_text: str,
    mvp_name: str,
    mvp_text: str,
) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if manual_text:
            zf.writestr(manual_name, manual_text)
            zf.writestr(manual_name.replace(".md", ".txt"), manual_text)
        if process_text:
            zf.writestr(process_name, process_text)
            zf.writestr(process_name.replace(".md", ".txt"), process_text)
        if mvp_text:
            zf.writestr(mvp_name, mvp_text)
            zf.writestr(mvp_name.replace(".md", ".txt"), mvp_text)
    return buffer.getvalue()


@st.cache_data(show_spinner=False)
def load_rule_source_map(path_value: str, mtime: float = 0.0) -> dict[str, dict[str, str]]:
    _ = mtime
    path_obj = Path(path_value)
    if not path_obj.exists():
        return {}
    try:
        import json

        payload = json.loads(path_obj.read_text(encoding="utf-8"))
        result: dict[str, dict[str, str]] = {}
        for rule in list(payload.get("rules") or []):
            rid = str(rule.get("id") or "").strip()
            if not rid:
                continue
            result[rid] = {
                "source": str(rule.get("source") or "manual"),
                "recommendation": str(rule.get("recommendation") or ""),
            }
        return result
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def load_manual_page_title_map(path_value: str, mtime: float = 0.0) -> dict[str, str]:
    _ = mtime
    path_obj = Path(path_value)
    if not path_obj.exists():
        return {}
    result: dict[str, str] = {}
    try:
        text = path_obj.read_text(encoding="utf-8")
        for line in text.splitlines():
            match = re.match(r"^##\s+p(\d{2})\.\s*(.+)$", line.strip())
            if not match:
                continue
            page_no = f"p{match.group(1)}"
            title = str(match.group(2) or "").strip()
            result[page_no] = title
    except Exception:
        return {}
    return result


@st.cache_data(show_spinner=False)
def split_manual_sections(manual_text: str) -> dict[str, str]:
    text = str(manual_text or "")
    if not text.strip():
        return {}
    pattern = r"(?ms)^##\s+(p\d{2})\..*?(?=^##\s+p\d{2}\.|^##\s+규칙 데이터화 매핑 표|\Z)"
    matches = re.finditer(pattern, text)
    sections: dict[str, str] = {}
    for m in matches:
        key = str(m.group(1) or "").strip()
        body = str(m.group(0) or "").strip()
        if key and body:
            sections[key] = body
    return sections


# API Key 관리
if "api_key" not in st.session_state:
    st.session_state.api_key = resolve_api_key()

# ==================== 데이터 강화 함수 ====================
def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in DEFAULT_COLUMNS:
        if col not in result.columns: 
            result[col] = ""
            
    for idx, row in result.iterrows():
        try:
            row_dict = row.to_dict()
            score = calculate_candidate_score(row_dict)
            grade = classify_grade(score)

            result.at[idx, "분석점수"] = score
            result.at[idx, "분석등급"] = grade

            if not str(row.get("권리요약") or "").strip():
                result.at[idx, "권리요약"] = build_rights_summary(row_dict)

            row_dict_updated = result.loc[idx].to_dict()

            debt = _safe_float(row_dict_updated.get("부채총액", 0))
            value = _safe_float(row_dict_updated.get("KB시세") or row_dict_updated.get("감정가", 0))
            ltv = (debt / value * 100) if value > 0 else 0
            result.at[idx, "추정LTV"] = f"{ltv:.1f}%"

            if not str(row.get("제안포인트") or "").strip():
                result.at[idx, "제안포인트"] = recommend_lender(row_dict_updated)

            try:
                policy_eval = evaluate_case_policy(row_dict_updated)
            except Exception:
                policy_eval = {"decision": "reject", "keep_data": False, "reason": "정책평가 실패"}

            try:
                market_ok = passes_market_filters(row_dict_updated) if not policy_eval.get("keep_data") else True
            except Exception:
                market_ok = False

            status_msg = "❌ 부적격 (Rejected)"
            if policy_eval.get("keep_data") and market_ok:
                status_msg = "✅ 적격 (Approved)"
            elif not policy_eval.get("keep_data"):
                status_msg = f"🗑️ 데이터보관제외 ({policy_eval.get('reason')})"
            else:
                status_msg = "⚠️ 부적격 (심사 기준 미달)"

            result.at[idx, "심사상태"] = status_msg

            if policy_eval.get("keep_data") and not str(row.get("담당자메모") or "").strip():
                creditor = str(row_dict_updated.get("주요채권자") or row_dict_updated.get("채권자") or "")
                guidance = get_creditor_analysis_guidance(creditor) if creditor else ""
                result.at[idx, "담당자메모"] = (
                    f"▶ 권리분석 기준: {policy_eval.get('reason')}\n"
                    f"▶ 채권자 분석: {guidance or '채권자별 패턴 누적 필요'}"
                )

            try:
                if needs_registry_verification(row_dict_updated):
                    result.at[idx, "등기부열람여부"] = "열람필수"
            except Exception:
                pass

            # MVP 규칙 엔진: 매뉴얼 규칙 데이터 기반 점수/판정/근거/취하 스크립트 생성
            try:
                manual_eval = evaluate_manual_rules(row_dict_updated)
                result.at[idx, "규칙버전"] = manual_eval.get("rule_version", "")
                result.at[idx, "규칙점수"] = manual_eval.get("score", "")
                result.at[idx, "규칙판정"] = manual_eval.get("verdict", "")
                result.at[idx, "규칙근거"] = " | ".join(manual_eval.get("evidence", [])[:6])
                result.at[idx, "취하스크립트"] = manual_eval.get("withdrawal_script", "")
            except Exception as rule_error:
                result.at[idx, "규칙판정"] = f"규칙엔진오류({type(rule_error).__name__})"

            if not str(row.get("담당자메모") or "").strip():
                result.at[idx, "담당자메모"] = f"▶ 실무 메모: {build_owner_pitch(row_dict_updated)}"

        except Exception as row_error:
            result.at[idx, "심사상태"] = f"⚠️ 보완필요 (행 처리 오류: {type(row_error).__name__})"
            if not str(result.at[idx, "담당자메모"] or "").strip():
                result.at[idx, "담당자메모"] = "▶ 행 처리 중 오류가 발생해 보수적으로 보완필요로 분류되었습니다."

    return result


def status_mask(frame: pd.DataFrame, keyword: str = "적격") -> pd.Series:
    if "심사상태" not in frame.columns:
        return pd.Series([False] * len(frame), index=frame.index)
    return frame["심사상태"].astype(str).str.contains(keyword, na=False)


def _split_pipe_values(raw_value: str, limit: int = 6) -> list[str]:
    text = str(raw_value or "")
    items = [item.strip() for item in text.split("|") if str(item).strip()]
    return items[:limit]


def _safe_days_value(raw_value: object) -> int:
    text = str(raw_value or "").strip()
    if not text:
        return 9999
    matched = re.search(r"-?\d+", text)
    if not matched:
        return 9999
    try:
        return int(matched.group(0))
    except Exception:
        return 9999


def _to_number(value: object) -> float:
    try:
        return float(str(value or "").replace(",", "").strip())
    except Exception:
        return -1.0


def _score_band_label(score_value: object) -> str:
    score = _to_number(score_value)
    if score < 0:
        return "미생성"
    if score >= 75:
        return "상(75+)"
    if score >= 55:
        return "중(55-74)"
    return "하(0-54)"


def _creditor_type_label(creditor_name: object) -> str:
    text = str(creditor_name or "").replace(" ", "")
    if not text:
        return "미상"
    if any(k in text for k in ["은행", "농협", "수협", "중앙회"]):
        return "1금융"
    if any(k in text for k in ["저축", "캐피탈", "대부", "파이낸셜"]):
        return "2/3금융"
    if any(k in text for k in ["유동화", "NPL", "npl", "자산관리"]):
        return "유동화/NPL"
    if any(k in text for k in ["세무서", "구청", "시청", "건강보험"]):
        return "공공"
    return "일반"


def render_rule_execution_cards(frame: pd.DataFrame, max_cards: int = 8) -> None:
    if frame.empty:
        return

    st.markdown("### 🧩 규칙 실행 결과 요약 카드")
    st.caption("실패 규칙 ID, 권고문, 취하 스크립트를 사건 단위로 빠르게 확인할 수 있습니다.")

    rulepack_path = Path(__file__).resolve().parent / "data" / "manual_rules_mvp_v1.json"
    manual_path = Path(__file__).resolve().parent / "docs" / "05_MVP_권리분석32p_취하18p_초안_v1.md"
    source_map = load_rule_source_map(
        str(rulepack_path),
        rulepack_path.stat().st_mtime if rulepack_path.exists() else 0.0,
    )
    page_title_map = load_manual_page_title_map(
        str(manual_path),
        manual_path.stat().st_mtime if manual_path.exists() else 0.0,
    )

    sorted_frame = frame.copy()
    sorted_frame["_rule_score_num"] = pd.to_numeric(sorted_frame.get("규칙점수", ""), errors="coerce").fillna(-1)
    sorted_frame["_days_left_num"] = sorted_frame.get("잔여일수", "").map(_safe_days_value)
    sorted_frame["_verdict"] = sorted_frame.get("규칙판정", "").astype(str)
    sorted_frame["_creditor_type"] = sorted_frame.get("주요채권자", "").map(_creditor_type_label)
    sorted_frame["_score_band"] = sorted_frame.get("규칙점수", "").map(_score_band_label)

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        verdict_filter = st.selectbox(
            "판정 필터",
            options=["전체", "GO", "HOLD", "DROP"],
            index=0,
            key="rule_card_filter_verdict",
        )
    with filter_col2:
        creditor_filter = st.selectbox(
            "채권자 유형 필터",
            options=["전체", "1금융", "2/3금융", "유동화/NPL", "공공", "일반", "미상"],
            index=0,
            key="rule_card_filter_creditor",
        )
    with filter_col3:
        score_filter = st.selectbox(
            "점수 구간 필터",
            options=["전체", "상(75+)", "중(55-74)", "하(0-54)", "미생성"],
            index=0,
            key="rule_card_filter_score",
        )

    if verdict_filter != "전체":
        sorted_frame = sorted_frame[sorted_frame["_verdict"] == verdict_filter]
    if creditor_filter != "전체":
        sorted_frame = sorted_frame[sorted_frame["_creditor_type"] == creditor_filter]
    if score_filter != "전체":
        sorted_frame = sorted_frame[sorted_frame["_score_band"] == score_filter]

    if sorted_frame.empty:
        st.info("선택한 필터에 해당하는 사건이 없습니다.")
        return

    sorted_frame = sorted_frame.sort_values(by=["_rule_score_num", "_days_left_num"], ascending=[True, True])
    preview_rows = sorted_frame.head(max_cards)

    for _, row in preview_rows.iterrows():
        row_dict = row.to_dict()
        case_no = str(row.get("사건번호") or "미상")
        verdict = str(row.get("규칙판정") or "미생성")
        score = str(row.get("규칙점수") or "-")
        failed_ids: list[str] = []
        recommendations: list[str] = []
        evidences: list[str] = []
        withdrawal_script = str(row.get("취하스크립트") or "")

        try:
            eval_result = evaluate_manual_rules(row_dict)
            failed_ids = eval_result.get("failed_rule_ids", [])[:6]
            recommendations = eval_result.get("recommendations", [])[:3]
            evidences = eval_result.get("evidence", [])
            if not withdrawal_script.strip():
                withdrawal_script = str(eval_result.get("withdrawal_script") or "")
        except Exception:
            failed_ids = []
            recommendations = []
            evidences = []

        if not failed_ids:
            failed_ids = _split_pipe_values(row.get("규칙근거", ""), limit=4)

        with st.container(border=True):
            head_col1, head_col2, head_col3 = st.columns([2, 1, 1])
            with head_col1:
                st.markdown(f"**사건번호:** {case_no}")
            with head_col2:
                st.markdown(f"**규칙판정:** {verdict}")
            with head_col3:
                st.markdown(f"**규칙점수:** {score}")

            st.markdown("**실패 규칙 ID/근거 요약**")
            if failed_ids:
                for rid in failed_ids:
                    rid_text = str(rid)
                    src_info = source_map.get(rid_text, {})
                    src = str(src_info.get("source") or "")
                    rec = str(src_info.get("recommendation") or "")

                    page_hint = ""
                    page_match = re.search(r"p\d{2}", src)
                    if page_match:
                        page_key = page_match.group(0)
                        page_title = page_title_map.get(page_key, "")
                        if page_title:
                            page_hint = f" / {page_key} {page_title}"
                        else:
                            page_hint = f" / {page_key}"

                    line = f"- {rid_text}"
                    if src:
                        line += f" -> {src}{page_hint}"
                    st.write(line)
                    if rec:
                        st.caption(f"권고: {rec}")

                    evidence_line = ""
                    for ev in evidences:
                        ev_text = str(ev)
                        if rid_text in ev_text:
                            evidence_line = ev_text
                            break
                    if evidence_line:
                        with st.expander(f"근거 상세 {rid_text}", expanded=False):
                            st.code(evidence_line)
            else:
                st.write("없음")

            st.markdown("**권고문 요약**")
            if recommendations:
                for rec in recommendations:
                    st.write(f"- {rec}")
            else:
                st.write("권고문 없음")

            st.markdown("**취하 스크립트(요약)**")
            if withdrawal_script.strip():
                st.info(withdrawal_script[:280])
            else:
                st.info("생성된 스크립트가 없습니다.")

# =========================================================================
# SECTION 1: 업로드 및 AI 파싱
# =========================================================================
st.markdown("<div class='section-title'>📁 PC/모바일 캡처 업로드 및 자동 정리</div>", unsafe_allow_html=True)

st.info(
    "📌 운영 규칙: 기준 미달 사건은 플랫폼이 데이터에서 삭제하고, 기준을 충족하는 사건만 보관합니다. "
    "취하 진행이 없거나 실무상 부적격으로 판정된 사건은 사용자가 삭제할 수 있습니다."
)

try:
    rule_meta = get_rulepack_meta()
    st.caption(
        f"활성 규칙팩: {rule_meta.get('rule_version')} "
        f"/ 규칙 수: {rule_meta.get('rule_count')}"
    )
except Exception:
    st.caption("활성 규칙팩 정보를 불러오지 못했습니다.")

st.markdown("### 🧭 실무 흐름 요약")
flow_col1, flow_col2, flow_col3 = st.columns(3)
with flow_col1:
    st.info(
        "1. 사건 구조 파악\n"
        "- 물건 정보, 권리관계, 점유자, 채권자, 진행 단계 확인"
    )
with flow_col2:
    st.info(
        "2. 리스크와 수치 해석\n"
        "- 부채·시세·낙찰가를 비교해 실무적 부담과 회수 가능성 정리"
    )
with flow_col3:
    st.info(
        "3. 대응 포인트 정리\n"
        "- 근거, 리스크, 행동안을 묶어 실전 브리핑과 유도 문구로 구성"
    )

with st.expander("📘 권리분석 고도화 매뉴얼(실무 학습용)", expanded=False):
    manual_100p_path = Path(__file__).resolve().parent / "docs" / "04_권리분석_실무_매뉴얼_100p.md"
    manual_process_path = Path(__file__).resolve().parent / "docs" / "04_권리분석_실무와_경매_취하_유도_프로세스.md"
    manual_mvp_path = Path(__file__).resolve().parent / "docs" / "05_MVP_권리분석32p_취하18p_검수본_v2.md"
    manual_p01_path = Path(__file__).resolve().parent / "docs" / "01_p01_사건식별_검수표_v1.md"
    manual_p02_path = Path(__file__).resolve().parent / "docs" / "02_p02_사건번호정규화_검수표_v1.md"
    manual_p03_path = Path(__file__).resolve().parent / "docs" / "03_p03_법원주소정합성_검수표_v1.md"
    manual_p04_path = Path(__file__).resolve().parent / "docs" / "04_p04_감정가하한필터_검수표_v1.md"
    manual_p05_path = Path(__file__).resolve().parent / "docs" / "05_p05_감정가상한분리_검수표_v1.md"
    manual_p06_path = Path(__file__).resolve().parent / "docs" / "06_p06_수도권범위제한_검수표_v1.md"
    manual_p07_path = Path(__file__).resolve().parent / "docs" / "07_p07_부채총액필수화_검수표_v1.md"
    manual_p08_path = Path(__file__).resolve().parent / "docs" / "08_p08_시세필수화_검수표_v1.md"
    manual_p09_path = Path(__file__).resolve().parent / "docs" / "09_p09_LTV상한규칙_검수표_v1.md"
    manual_p10_path = Path(__file__).resolve().parent / "docs" / "10_p10_권리리스크개수상한_검수표_v1.md"
    manual_p11_path = Path(__file__).resolve().parent / "docs" / "11_p11_매각기일잔여일수신뢰성_검수표_v1.md"
    manual_p12_path = Path(__file__).resolve().parent / "docs" / "12_p12_물건번호사건번호연결검증_검수표_v1.md"
    manual_p13_path = Path(__file__).resolve().parent / "docs" / "13_p13_권리요약생성품질검증_검수표_v1.md"
    manual_p14_path = Path(__file__).resolve().parent / "docs" / "14_p14_주요채권자추출검증_검수표_v1.md"
    manual_p15_path = Path(__file__).resolve().parent / "docs" / "15_p15_최저매각가격정합성_검수표_v1.md"
    manual_p16_path = Path(__file__).resolve().parent / "docs" / "16_p16_낙찰예상가필수화_검수표_v1.md"
    manual_p17_path = Path(__file__).resolve().parent / "docs" / "17_p17_부채시세역전경고_검수표_v1.md"
    manual_p18_path = Path(__file__).resolve().parent / "docs" / "18_p18_등기부열람필수분기_검수표_v1.md"
    manual_p19_path = Path(__file__).resolve().parent / "docs" / "19_p19_아파트명주소토큰정합성_검수표_v1.md"
    manual_p20_path = Path(__file__).resolve().parent / "docs" / "20_p20_분석가능상태확정_검수표_v1.md"
    manual_p21_path = Path(__file__).resolve().parent / "docs" / "21_p21_권리리스크점수화_검수표_v1.md"
    manual_p22_path = Path(__file__).resolve().parent / "docs" / "22_p22_명도리스크입력검증_검수표_v1.md"
    manual_p23_path = Path(__file__).resolve().parent / "docs" / "23_p23_배당비교입력세트확인_검수표_v1.md"
    manual_p24_path = Path(__file__).resolve().parent / "docs" / "24_p24_사건단계라벨링_검수표_v1.md"
    manual_p25_path = Path(__file__).resolve().parent / "docs" / "25_p25_유찰반영낙찰예상가보정_검수표_v1.md"
    manual_p26_path = Path(__file__).resolve().parent / "docs" / "26_p26_LTV경계구간경고_검수표_v1.md"
    manual_p27_path = Path(__file__).resolve().parent / "docs" / "27_p27_권리채권자일치검증_검수표_v1.md"
    manual_p28_path = Path(__file__).resolve().parent / "docs" / "28_p28_고가물건30억관리규칙_검수표_v1.md"
    manual_p29_path = Path(__file__).resolve().parent / "docs" / "29_p29_분석근거최소수량규칙_검수표_v1.md"
    manual_100p_name = "04_권리분석_실무_매뉴얼_100p.md"
    manual_process_name = "04_권리분석_실무와_경매_취하_유도_프로세스.md"
    manual_mvp_name = "05_MVP_권리분석32p_취하18p_검수본_v2.md"
    manual_p01_name = "01_p01_사건식별_검수표_v1.md"
    manual_p02_name = "02_p02_사건번호정규화_검수표_v1.md"
    manual_p03_name = "03_p03_법원주소정합성_검수표_v1.md"
    manual_p04_name = "04_p04_감정가하한필터_검수표_v1.md"
    manual_p05_name = "05_p05_감정가상한분리_검수표_v1.md"
    manual_p06_name = "06_p06_수도권범위제한_검수표_v1.md"
    manual_p07_name = "07_p07_부채총액필수화_검수표_v1.md"
    manual_p08_name = "08_p08_시세필수화_검수표_v1.md"
    manual_p09_name = "09_p09_LTV상한규칙_검수표_v1.md"
    manual_p10_name = "10_p10_권리리스크개수상한_검수표_v1.md"
    manual_p11_name = "11_p11_매각기일잔여일수신뢰성_검수표_v1.md"
    manual_p12_name = "12_p12_물건번호사건번호연결검증_검수표_v1.md"
    manual_p13_name = "13_p13_권리요약생성품질검증_검수표_v1.md"
    manual_p14_name = "14_p14_주요채권자추출검증_검수표_v1.md"
    manual_p15_name = "15_p15_최저매각가격정합성_검수표_v1.md"
    manual_p16_name = "16_p16_낙찰예상가필수화_검수표_v1.md"
    manual_p17_name = "17_p17_부채시세역전경고_검수표_v1.md"
    manual_p18_name = "18_p18_등기부열람필수분기_검수표_v1.md"
    manual_p19_name = "19_p19_아파트명주소토큰정합성_검수표_v1.md"
    manual_p20_name = "20_p20_분석가능상태확정_검수표_v1.md"
    manual_p21_name = "21_p21_권리리스크점수화_검수표_v1.md"
    manual_p22_name = "22_p22_명도리스크입력검증_검수표_v1.md"
    manual_p23_name = "23_p23_배당비교입력세트확인_검수표_v1.md"
    manual_p24_name = "24_p24_사건단계라벨링_검수표_v1.md"
    manual_p25_name = "25_p25_유찰반영낙찰예상가보정_검수표_v1.md"
    manual_p26_name = "26_p26_LTV경계구간경고_검수표_v1.md"
    manual_p27_name = "27_p27_권리채권자일치검증_검수표_v1.md"
    manual_p28_name = "28_p28_고가물건30억관리규칙_검수표_v1.md"
    manual_p29_name = "29_p29_분석근거최소수량규칙_검수표_v1.md"

    manual_100p_text = ""
    manual_process_text = ""
    manual_mvp_text = ""
    manual_p01_text = ""
    manual_p02_text = ""
    manual_p03_text = ""
    manual_p04_text = ""
    manual_p05_text = ""
    manual_p06_text = ""
    manual_p07_text = ""
    manual_p08_text = ""
    manual_p09_text = ""
    manual_p10_text = ""
    manual_p11_text = ""
    manual_p12_text = ""
    manual_p13_text = ""
    manual_p14_text = ""
    manual_p15_text = ""
    manual_p16_text = ""
    manual_p17_text = ""
    manual_p18_text = ""
    manual_p19_text = ""
    manual_p20_text = ""
    manual_p21_text = ""
    manual_p22_text = ""
    manual_p23_text = ""
    manual_p24_text = ""
    manual_p25_text = ""
    manual_p26_text = ""
    manual_p27_text = ""
    manual_p28_text = ""
    manual_p29_text = ""
    try:
        manual_100p_text = read_utf8_text_file(
            str(manual_100p_path),
            manual_100p_path.stat().st_mtime if manual_100p_path.exists() else 0.0,
        )
        manual_process_text = read_utf8_text_file(
            str(manual_process_path),
            manual_process_path.stat().st_mtime if manual_process_path.exists() else 0.0,
        )
        manual_mvp_text = read_utf8_text_file(
            str(manual_mvp_path),
            manual_mvp_path.stat().st_mtime if manual_mvp_path.exists() else 0.0,
        )
        manual_p01_text = read_utf8_text_file(
            str(manual_p01_path),
            manual_p01_path.stat().st_mtime if manual_p01_path.exists() else 0.0,
        )
        manual_p02_text = read_utf8_text_file(
            str(manual_p02_path),
            manual_p02_path.stat().st_mtime if manual_p02_path.exists() else 0.0,
        )
        manual_p03_text = read_utf8_text_file(
            str(manual_p03_path),
            manual_p03_path.stat().st_mtime if manual_p03_path.exists() else 0.0,
        )
        manual_p04_text = read_utf8_text_file(
            str(manual_p04_path),
            manual_p04_path.stat().st_mtime if manual_p04_path.exists() else 0.0,
        )
        manual_p05_text = read_utf8_text_file(
            str(manual_p05_path),
            manual_p05_path.stat().st_mtime if manual_p05_path.exists() else 0.0,
        )
        manual_p06_text = read_utf8_text_file(
            str(manual_p06_path),
            manual_p06_path.stat().st_mtime if manual_p06_path.exists() else 0.0,
        )
        manual_p07_text = read_utf8_text_file(
            str(manual_p07_path),
            manual_p07_path.stat().st_mtime if manual_p07_path.exists() else 0.0,
        )
        manual_p08_text = read_utf8_text_file(
            str(manual_p08_path),
            manual_p08_path.stat().st_mtime if manual_p08_path.exists() else 0.0,
        )
        manual_p09_text = read_utf8_text_file(
            str(manual_p09_path),
            manual_p09_path.stat().st_mtime if manual_p09_path.exists() else 0.0,
        )
        manual_p10_text = read_utf8_text_file(
            str(manual_p10_path),
            manual_p10_path.stat().st_mtime if manual_p10_path.exists() else 0.0,
        )
        manual_p11_text = read_utf8_text_file(
            str(manual_p11_path),
            manual_p11_path.stat().st_mtime if manual_p11_path.exists() else 0.0,
        )
        manual_p12_text = read_utf8_text_file(
            str(manual_p12_path),
            manual_p12_path.stat().st_mtime if manual_p12_path.exists() else 0.0,
        )
        manual_p13_text = read_utf8_text_file(
            str(manual_p13_path),
            manual_p13_path.stat().st_mtime if manual_p13_path.exists() else 0.0,
        )
        manual_p14_text = read_utf8_text_file(
            str(manual_p14_path),
            manual_p14_path.stat().st_mtime if manual_p14_path.exists() else 0.0,
        )
        manual_p15_text = read_utf8_text_file(
            str(manual_p15_path),
            manual_p15_path.stat().st_mtime if manual_p15_path.exists() else 0.0,
        )
        manual_p16_text = read_utf8_text_file(
            str(manual_p16_path),
            manual_p16_path.stat().st_mtime if manual_p16_path.exists() else 0.0,
        )
        manual_p17_text = read_utf8_text_file(
            str(manual_p17_path),
            manual_p17_path.stat().st_mtime if manual_p17_path.exists() else 0.0,
        )
        manual_p18_text = read_utf8_text_file(
            str(manual_p18_path),
            manual_p18_path.stat().st_mtime if manual_p18_path.exists() else 0.0,
        )
        manual_p19_text = read_utf8_text_file(
            str(manual_p19_path),
            manual_p19_path.stat().st_mtime if manual_p19_path.exists() else 0.0,
        )
        manual_p20_text = read_utf8_text_file(
            str(manual_p20_path),
            manual_p20_path.stat().st_mtime if manual_p20_path.exists() else 0.0,
        )
        manual_p21_text = read_utf8_text_file(
            str(manual_p21_path),
            manual_p21_path.stat().st_mtime if manual_p21_path.exists() else 0.0,
        )
        manual_p22_text = read_utf8_text_file(
            str(manual_p22_path),
            manual_p22_path.stat().st_mtime if manual_p22_path.exists() else 0.0,
        )
        manual_p23_text = read_utf8_text_file(
            str(manual_p23_path),
            manual_p23_path.stat().st_mtime if manual_p23_path.exists() else 0.0,
        )
        manual_p24_text = read_utf8_text_file(
            str(manual_p24_path),
            manual_p24_path.stat().st_mtime if manual_p24_path.exists() else 0.0,
        )
        manual_p25_text = read_utf8_text_file(
            str(manual_p25_path),
            manual_p25_path.stat().st_mtime if manual_p25_path.exists() else 0.0,
        )
        manual_p26_text = read_utf8_text_file(
            str(manual_p26_path),
            manual_p26_path.stat().st_mtime if manual_p26_path.exists() else 0.0,
        )
        manual_p27_text = read_utf8_text_file(
            str(manual_p27_path),
            manual_p27_path.stat().st_mtime if manual_p27_path.exists() else 0.0,
        )
        manual_p28_text = read_utf8_text_file(
            str(manual_p28_path),
            manual_p28_path.stat().st_mtime if manual_p28_path.exists() else 0.0,
        )
        manual_p29_text = read_utf8_text_file(
            str(manual_p29_path),
            manual_p29_path.stat().st_mtime if manual_p29_path.exists() else 0.0,
        )
    except Exception as manual_error:
        st.warning(f"매뉴얼 파일을 읽는 중 오류가 발생했습니다: {type(manual_error).__name__}")

    st.markdown("### 권리분석 고도화 매뉴얼")
    st.info("검수 기준 문서는 p01 단일 검수표입니다. 전체 매뉴얼은 뒤에서 참고용으로만 엽니다.")

    if manual_p01_text:
        st.markdown("#### ✅ 현재 검수 기준: p01 사건 식별")
        p01_col1, p01_col2 = st.columns(2)
        with p01_col1:
            st.download_button(
                "📥 p01 검수표 다운로드 (MD)",
                data=manual_p01_text,
                file_name=manual_p01_name,
                mime="text/markdown",
                use_container_width=True,
            )
        with p01_col2:
            st.download_button(
                "📥 p01 검수표 다운로드 (TXT)",
                data=manual_p01_text,
                file_name=manual_p01_name.replace(".md", ".txt"),
                mime="text/plain",
                use_container_width=True,
            )

        st.markdown(manual_p01_text)
    else:
        st.warning("p01 검수표 파일을 읽지 못했습니다. docs 경로를 확인해 주세요.")

    if manual_p02_text:
        with st.expander("다음 검수 페이지: p02 사건번호 정규화", expanded=False):
            p02_col1, p02_col2 = st.columns(2)
            with p02_col1:
                st.download_button(
                    "📥 p02 검수표 다운로드 (MD)",
                    data=manual_p02_text,
                    file_name=manual_p02_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p02_col2:
                st.download_button(
                    "📥 p02 검수표 다운로드 (TXT)",
                    data=manual_p02_text,
                    file_name=manual_p02_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p02_text)

    with st.expander("전체 매뉴얼 검토", expanded=False):
        if manual_mvp_text:
            st.download_button(
                "📥 전체 매뉴얼 다운로드 (MD)",
                data=manual_mvp_text,
                file_name=manual_mvp_name,
                mime="text/markdown",
                use_container_width=True,
            )
            st.markdown(manual_mvp_text[:12000])

        if manual_100p_text:
            st.download_button(
                "📥 100p 참고문서 다운로드 (MD)",
                data=manual_100p_text,
                file_name=manual_100p_name,
                mime="text/markdown",
                use_container_width=True,
            )

        if manual_process_text:
            st.download_button(
                "📥 보조 문서 다운로드 (MD)",
                data=manual_process_text,
                file_name=manual_process_name,
                mime="text/markdown",
                use_container_width=True,
            )

    show_archive_docs = st.checkbox(
        "아카이브 문서 표시",
        value=False,
        key="show_archive_docs_toggle",
        help="기본 검수 화면에서는 숨깁니다.",
    )

    if show_archive_docs:
        with st.expander("📚 아카이브 문서", expanded=False):
            if manual_100p_text:
                legacy_col1, legacy_col2 = st.columns(2)
                with legacy_col1:
                    st.download_button(
                        "📥 100p 참고문서 다운로드 (MD)",
                        data=manual_100p_text,
                        file_name=manual_100p_name,
                        mime="text/markdown",
                        use_container_width=True,
                    )
                with legacy_col2:
                    st.download_button(
                        "📥 100p 참고문서 다운로드 (TXT)",
                        data=manual_100p_text,
                        file_name=manual_100p_name.replace(".md", ".txt"),
                        mime="text/plain",
                        use_container_width=True,
                    )

                enable_manual_preview = st.checkbox(
                    "100p 참고문서 미리보기 로드",
                    value=False,
                    key="manual_preview_toggle",
                    help="기본 OFF로 두고 필요 시에만 렌더링합니다.",
                )
                if enable_manual_preview:
                    page_size = 7000
                    total_pages = max(1, (len(manual_100p_text) + page_size - 1) // page_size)
                    selected_page = st.number_input(
                        "100p 문서 조각 번호",
                        min_value=1,
                        max_value=total_pages,
                        value=1,
                        step=1,
                    )
                    start = (selected_page - 1) * page_size
                    end = min(len(manual_100p_text), start + page_size)
                    st.caption(f"표시 구간: {start + 1:,} ~ {end:,} / 전체 {len(manual_100p_text):,}자")
                    st.markdown(manual_100p_text[start:end])
            else:
                st.caption("100p 참고문서는 현재 비어 있습니다.")

    if manual_p03_text:
        with st.expander("다음 검수 페이지: p03 법원/주소 정합성", expanded=False):
            p03_col1, p03_col2 = st.columns(2)
            with p03_col1:
                st.download_button(
                    "📥 p03 검수표 다운로드 (MD)",
                    data=manual_p03_text,
                    file_name=manual_p03_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p03_col2:
                st.download_button(
                    "📥 p03 검수표 다운로드 (TXT)",
                    data=manual_p03_text,
                    file_name=manual_p03_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p03_text)

    if manual_p04_text:
        with st.expander("다음 검수 페이지: p04 감정가 하한 필터", expanded=False):
            p04_col1, p04_col2 = st.columns(2)
            with p04_col1:
                st.download_button(
                    "📥 p04 검수표 다운로드 (MD)",
                    data=manual_p04_text,
                    file_name=manual_p04_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p04_col2:
                st.download_button(
                    "📥 p04 검수표 다운로드 (TXT)",
                    data=manual_p04_text,
                    file_name=manual_p04_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p04_text)

    if manual_p05_text:
        with st.expander("다음 검수 페이지: p05 감정가 상한 분리", expanded=False):
            p05_col1, p05_col2 = st.columns(2)
            with p05_col1:
                st.download_button(
                    "📥 p05 검수표 다운로드 (MD)",
                    data=manual_p05_text,
                    file_name=manual_p05_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p05_col2:
                st.download_button(
                    "📥 p05 검수표 다운로드 (TXT)",
                    data=manual_p05_text,
                    file_name=manual_p05_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p05_text)

            if manual_process_text:
                st.download_button(
                    "📥 보조 문서 다운로드 (MD)",
                    data=manual_process_text,
                    file_name="04_권리분석_실무와_경매_취하_유도_프로세스.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

    if manual_p06_text:
        with st.expander("다음 검수 페이지: p06 수도권 범위 제한", expanded=False):
            p06_col1, p06_col2 = st.columns(2)
            with p06_col1:
                st.download_button(
                    "📥 p06 검수표 다운로드 (MD)",
                    data=manual_p06_text,
                    file_name=manual_p06_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p06_col2:
                st.download_button(
                    "📥 p06 검수표 다운로드 (TXT)",
                    data=manual_p06_text,
                    file_name=manual_p06_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p06_text)

    if manual_p07_text:
        with st.expander("다음 검수 페이지: p07 부채총액 필수화", expanded=False):
            p07_col1, p07_col2 = st.columns(2)
            with p07_col1:
                st.download_button(
                    "📥 p07 검수표 다운로드 (MD)",
                    data=manual_p07_text,
                    file_name=manual_p07_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p07_col2:
                st.download_button(
                    "📥 p07 검수표 다운로드 (TXT)",
                    data=manual_p07_text,
                    file_name=manual_p07_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p07_text)

    if manual_p08_text:
        with st.expander("다음 검수 페이지: p08 시세 필수화", expanded=False):
            p08_col1, p08_col2 = st.columns(2)
            with p08_col1:
                st.download_button(
                    "📥 p08 검수표 다운로드 (MD)",
                    data=manual_p08_text,
                    file_name=manual_p08_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p08_col2:
                st.download_button(
                    "📥 p08 검수표 다운로드 (TXT)",
                    data=manual_p08_text,
                    file_name=manual_p08_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p08_text)

    if manual_p09_text:
        with st.expander("다음 검수 페이지: p09 LTV 상한 규칙", expanded=False):
            p09_col1, p09_col2 = st.columns(2)
            with p09_col1:
                st.download_button(
                    "📥 p09 검수표 다운로드 (MD)",
                    data=manual_p09_text,
                    file_name=manual_p09_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p09_col2:
                st.download_button(
                    "📥 p09 검수표 다운로드 (TXT)",
                    data=manual_p09_text,
                    file_name=manual_p09_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p09_text)

    if manual_p10_text:
        with st.expander("다음 검수 페이지: p10 권리리스크 개수 상한", expanded=False):
            p10_col1, p10_col2 = st.columns(2)
            with p10_col1:
                st.download_button(
                    "📥 p10 검수표 다운로드 (MD)",
                    data=manual_p10_text,
                    file_name=manual_p10_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p10_col2:
                st.download_button(
                    "📥 p10 검수표 다운로드 (TXT)",
                    data=manual_p10_text,
                    file_name=manual_p10_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p10_text)

    if manual_p11_text:
        with st.expander("다음 검수 페이지: p11 매각기일/잔여일수 신뢰성 검증", expanded=False):
            p11_col1, p11_col2 = st.columns(2)
            with p11_col1:
                st.download_button(
                    "📥 p11 검수표 다운로드 (MD)",
                    data=manual_p11_text,
                    file_name=manual_p11_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p11_col2:
                st.download_button(
                    "📥 p11 검수표 다운로드 (TXT)",
                    data=manual_p11_text,
                    file_name=manual_p11_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p11_text)

    if manual_p12_text:
        with st.expander("다음 검수 페이지: p12 물건번호/사건번호 연결 검증", expanded=False):
            p12_col1, p12_col2 = st.columns(2)
            with p12_col1:
                st.download_button(
                    "📥 p12 검수표 다운로드 (MD)",
                    data=manual_p12_text,
                    file_name=manual_p12_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p12_col2:
                st.download_button(
                    "📥 p12 검수표 다운로드 (TXT)",
                    data=manual_p12_text,
                    file_name=manual_p12_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p12_text)

    if manual_p13_text:
        with st.expander("다음 검수 페이지: p13 권리요약 생성 품질 검증", expanded=False):
            p13_col1, p13_col2 = st.columns(2)
            with p13_col1:
                st.download_button(
                    "📥 p13 검수표 다운로드 (MD)",
                    data=manual_p13_text,
                    file_name=manual_p13_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p13_col2:
                st.download_button(
                    "📥 p13 검수표 다운로드 (TXT)",
                    data=manual_p13_text,
                    file_name=manual_p13_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p13_text)

    if manual_p14_text:
        with st.expander("다음 검수 페이지: p14 주요채권자 추출 검증", expanded=False):
            p14_col1, p14_col2 = st.columns(2)
            with p14_col1:
                st.download_button(
                    "📥 p14 검수표 다운로드 (MD)",
                    data=manual_p14_text,
                    file_name=manual_p14_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p14_col2:
                st.download_button(
                    "📥 p14 검수표 다운로드 (TXT)",
                    data=manual_p14_text,
                    file_name=manual_p14_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p14_text)

    if manual_p15_text:
        with st.expander("다음 검수 페이지: p15 최저매각가격 정합성", expanded=False):
            p15_col1, p15_col2 = st.columns(2)
            with p15_col1:
                st.download_button(
                    "📥 p15 검수표 다운로드 (MD)",
                    data=manual_p15_text,
                    file_name=manual_p15_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p15_col2:
                st.download_button(
                    "📥 p15 검수표 다운로드 (TXT)",
                    data=manual_p15_text,
                    file_name=manual_p15_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p15_text)

    if manual_p16_text:
        with st.expander("다음 검수 페이지: p16 낙찰예상가 필수화", expanded=False):
            p16_col1, p16_col2 = st.columns(2)
            with p16_col1:
                st.download_button(
                    "📥 p16 검수표 다운로드 (MD)",
                    data=manual_p16_text,
                    file_name=manual_p16_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p16_col2:
                st.download_button(
                    "📥 p16 검수표 다운로드 (TXT)",
                    data=manual_p16_text,
                    file_name=manual_p16_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p16_text)

    if manual_p17_text:
        with st.expander("다음 검수 페이지: p17 부채/시세 역전 경고", expanded=False):
            p17_col1, p17_col2 = st.columns(2)
            with p17_col1:
                st.download_button(
                    "📥 p17 검수표 다운로드 (MD)",
                    data=manual_p17_text,
                    file_name=manual_p17_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p17_col2:
                st.download_button(
                    "📥 p17 검수표 다운로드 (TXT)",
                    data=manual_p17_text,
                    file_name=manual_p17_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p17_text)

    if manual_p18_text:
        with st.expander("다음 검수 페이지: p18 등기부 열람필수 분기", expanded=False):
            p18_col1, p18_col2 = st.columns(2)
            with p18_col1:
                st.download_button(
                    "📥 p18 검수표 다운로드 (MD)",
                    data=manual_p18_text,
                    file_name=manual_p18_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p18_col2:
                st.download_button(
                    "📥 p18 검수표 다운로드 (TXT)",
                    data=manual_p18_text,
                    file_name=manual_p18_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p18_text)

    if manual_p19_text:
        with st.expander("다음 검수 페이지: p19 아파트명/주소 토큰 정합성", expanded=False):
            p19_col1, p19_col2 = st.columns(2)
            with p19_col1:
                st.download_button(
                    "📥 p19 검수표 다운로드 (MD)",
                    data=manual_p19_text,
                    file_name=manual_p19_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p19_col2:
                st.download_button(
                    "📥 p19 검수표 다운로드 (TXT)",
                    data=manual_p19_text,
                    file_name=manual_p19_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p19_text)

    if manual_p20_text:
        with st.expander("다음 검수 페이지: p20 분석 가능 상태 확정", expanded=False):
            p20_col1, p20_col2 = st.columns(2)
            with p20_col1:
                st.download_button(
                    "📥 p20 검수표 다운로드 (MD)",
                    data=manual_p20_text,
                    file_name=manual_p20_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p20_col2:
                st.download_button(
                    "📥 p20 검수표 다운로드 (TXT)",
                    data=manual_p20_text,
                    file_name=manual_p20_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p20_text)

    if manual_p21_text:
        with st.expander("다음 검수 페이지: p21 권리 리스크 점수화", expanded=False):
            p21_col1, p21_col2 = st.columns(2)
            with p21_col1:
                st.download_button(
                    "📥 p21 검수표 다운로드 (MD)",
                    data=manual_p21_text,
                    file_name=manual_p21_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p21_col2:
                st.download_button(
                    "📥 p21 검수표 다운로드 (TXT)",
                    data=manual_p21_text,
                    file_name=manual_p21_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p21_text)

    if manual_p22_text:
        with st.expander("다음 검수 페이지: p22 명도 리스크 입력 검증", expanded=False):
            p22_col1, p22_col2 = st.columns(2)
            with p22_col1:
                st.download_button(
                    "📥 p22 검수표 다운로드 (MD)",
                    data=manual_p22_text,
                    file_name=manual_p22_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p22_col2:
                st.download_button(
                    "📥 p22 검수표 다운로드 (TXT)",
                    data=manual_p22_text,
                    file_name=manual_p22_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p22_text)

    if manual_p23_text:
        with st.expander("다음 검수 페이지: p23 배당 비교 입력 세트 확인", expanded=False):
            p23_col1, p23_col2 = st.columns(2)
            with p23_col1:
                st.download_button(
                    "📥 p23 검수표 다운로드 (MD)",
                    data=manual_p23_text,
                    file_name=manual_p23_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p23_col2:
                st.download_button(
                    "📥 p23 검수표 다운로드 (TXT)",
                    data=manual_p23_text,
                    file_name=manual_p23_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p23_text)

    if manual_p24_text:
        with st.expander("다음 검수 페이지: p24 사건 단계 라벨링", expanded=False):
            p24_col1, p24_col2 = st.columns(2)
            with p24_col1:
                st.download_button(
                    "📥 p24 검수표 다운로드 (MD)",
                    data=manual_p24_text,
                    file_name=manual_p24_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p24_col2:
                st.download_button(
                    "📥 p24 검수표 다운로드 (TXT)",
                    data=manual_p24_text,
                    file_name=manual_p24_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p24_text)

    if manual_p25_text:
        with st.expander("다음 검수 페이지: p25 유찰 반영 낙찰예상가 보정", expanded=False):
            p25_col1, p25_col2 = st.columns(2)
            with p25_col1:
                st.download_button(
                    "📥 p25 검수표 다운로드 (MD)",
                    data=manual_p25_text,
                    file_name=manual_p25_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p25_col2:
                st.download_button(
                    "📥 p25 검수표 다운로드 (TXT)",
                    data=manual_p25_text,
                    file_name=manual_p25_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p25_text)

    if manual_p26_text:
        with st.expander("다음 검수 페이지: p26 LTV 경계구간 경고", expanded=False):
            p26_col1, p26_col2 = st.columns(2)
            with p26_col1:
                st.download_button(
                    "📥 p26 검수표 다운로드 (MD)",
                    data=manual_p26_text,
                    file_name=manual_p26_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p26_col2:
                st.download_button(
                    "📥 p26 검수표 다운로드 (TXT)",
                    data=manual_p26_text,
                    file_name=manual_p26_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p26_text)

    if manual_p27_text:
        with st.expander("다음 검수 페이지: p27 권리-채권자 일치 검증", expanded=False):
            p27_col1, p27_col2 = st.columns(2)
            with p27_col1:
                st.download_button(
                    "📥 p27 검수표 다운로드 (MD)",
                    data=manual_p27_text,
                    file_name=manual_p27_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p27_col2:
                st.download_button(
                    "📥 p27 검수표 다운로드 (TXT)",
                    data=manual_p27_text,
                    file_name=manual_p27_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p27_text)

    if manual_p28_text:
        with st.expander("다음 검수 페이지: p28 고가물건(30억+) 관리 규칙", expanded=False):
            p28_col1, p28_col2 = st.columns(2)
            with p28_col1:
                st.download_button(
                    "📥 p28 검수표 다운로드 (MD)",
                    data=manual_p28_text,
                    file_name=manual_p28_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p28_col2:
                st.download_button(
                    "📥 p28 검수표 다운로드 (TXT)",
                    data=manual_p28_text,
                    file_name=manual_p28_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p28_text)

    if manual_p29_text:
        with st.expander("다음 검수 페이지: p29 분석근거 최소 수량 규칙", expanded=False):
            p29_col1, p29_col2 = st.columns(2)
            with p29_col1:
                st.download_button(
                    "📥 p29 검수표 다운로드 (MD)",
                    data=manual_p29_text,
                    file_name=manual_p29_name,
                    mime="text/markdown",
                    use_container_width=True,
                )
            with p29_col2:
                st.download_button(
                    "📥 p29 검수표 다운로드 (TXT)",
                    data=manual_p29_text,
                    file_name=manual_p29_name.replace(".md", ".txt"),
                    mime="text/plain",
                    use_container_width=True,
                )
            st.markdown(manual_p29_text)

col_api1, col_api2 = st.columns([3, 1])
with col_api1:
    api_key_input = st.text_input(
        "🔑 Google Gemini API 키", 
        value=st.session_state.api_key, 
        type="password",
        help="API 키는 https://makersuite.google.com/app/apikey 에서 발급받으세요"
    )
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input

with col_api2:
    if st.session_state.api_key:
        st.success("🟢 API 키 활성화")
    else:
        st.error("🔴 API 키 필요")

st.markdown("---")

capture_files = st.file_uploader(
    "📸 캡처본 전용 드래그 업로드 (여러 장 가능, ZIP 지원)",
    type=["png", "jpg", "jpeg", "webp", "zip"],
    accept_multiple_files=True,
    key="capture_files_uploader",
    help="이미지 직접 업로드 또는 ZIP 일괄 업로드를 지원합니다.",
)

st.caption("붙여넣기는 드래그와 다릅니다. 아래 버튼/영역에서 Ctrl+V(Cmd+V)로 클립보드 이미지를 직접 추가할 수 있습니다.")
if paste_image_button is None:
    st.info("클립보드 붙여넣기 컴포넌트 로딩 전입니다. 배포 환경에서 자동 설치 후 활성화됩니다.")
else:
    paste_result = paste_image_button(
        label="📋 클립보드 이미지 붙여넣기 (Ctrl+V / Cmd+V)",
        key="clipboard_capture_paste",
    )
    new_clipboard_file = build_clipboard_upload(
        paste_result,
        index_hint=len(st.session_state.clipboard_images) + 1,
    )
    if new_clipboard_file is not None:
        st.session_state.clipboard_images.append(new_clipboard_file)
        st.success(f"클립보드 이미지 추가 완료: {new_clipboard_file.name}")

if st.session_state.clipboard_images:
    clip_cols = st.columns([3, 1])
    with clip_cols[0]:
        st.caption(f"클립보드 이미지 {len(st.session_state.clipboard_images)}장 대기 중")
    with clip_cols[1]:
        if st.button("클립보드 이미지 비우기", key="clear_clipboard_images"):
            st.session_state.clipboard_images = []
            st.session_state.clipboard_hashes = set()
            st.rerun()

data_files = st.file_uploader(
    "📊 데이터 파일 업로드 (CSV/XLSX)",
    type=["xlsx", "csv"],
    accept_multiple_files=True,
    key="data_files_uploader",
    help="엑셀/CSV를 함께 분석하려면 여기에 업로드하세요.",
)

uploaded_files = []
capture_image_files = []
zip_notice_messages = []

if capture_files:
    for cap in capture_files:
        cap_name = str(getattr(cap, "name", "") or "").lower()
        if cap_name.endswith(".zip"):
            extracted_images, zip_warnings = extract_images_from_zip(cap)
            capture_image_files.extend(extracted_images)
            zip_notice_messages.extend(zip_warnings)
            if extracted_images:
                st.success(f"ZIP 해제 완료: {cap.name} -> 이미지 {len(extracted_images)}장")
        else:
            capture_image_files.append(cap)

if zip_notice_messages:
    for msg in zip_notice_messages[:3]:
        st.warning(msg)

if capture_image_files:
    uploaded_files.extend(capture_image_files)
if st.session_state.clipboard_images:
    uploaded_files.extend(st.session_state.clipboard_images)
if data_files:
    uploaded_files.extend(data_files)

st.caption("권장 업로드 환경: PC 브라우저 드래그 업로드. 캡처와 CSV/XLSX는 분리 업로드가 더 안정적입니다.")

with st.expander("🧾 OCR 누락 시 필수 9개 필드 수동 보완 가이드", expanded=False):
    st.markdown(
        """
        아래 9개 필드만 채워도 심사 정확도가 크게 올라갑니다.

        - 사건번호
        - 법원명
        - 아파트명
        - 주소
        - 감정가
        - 부채총액
        - KB시세
        - 주요채권자
        - 근저당여부(예/아니오)
        """
    )
    st.code(
        """사건번호: 2024타경2979
법원명: 서울동부지방법원
아파트명: 태천해오름아파트
주소: 서울 강동구 천호동 52-17
감정가: 796000000
부채총액: 202774869
KB시세: 816000000
주요채권자: 유더블유제십오차유동화전문유한회사
근저당여부: 예""",
        language="text",
    )
    st.info("위 형식으로 텍스트를 복사해서 아래 '429 우회: 캡처 텍스트 직접 붙여넣기'에 넣으면, OCR이 놓친 값도 보완 분석할 수 있습니다.")

ocr_mode_label = st.selectbox(
    "🔎 캡처 인식 모드",
    options=["기본(균형)", "텍스트 우선(OCR 강화)"],
    index=1,
    help="텍스트 우선 모드는 표/문장 인식에 집중하기 위해 캡처를 분할·고대비 처리합니다."
)
ocr_mode = "text_first" if "텍스트 우선" in ocr_mode_label else "balanced"

ocr_engine_label = st.selectbox(
    "🧩 OCR 엔진",
    options=["자동(키 있으면 Gemini, 없으면 로컬 무료)", "Gemini Vision", "로컬 무료(PaddleOCR + Tesseract)"],
    index=0,
    help="로컬 무료 모드는 API 키 없이 동작하며, PaddleOCR 1차 + 저신뢰 구간 Tesseract 재시도로 보완합니다."
)
if "Gemini Vision" in ocr_engine_label:
    ocr_engine = "gemini"
elif "로컬 무료" in ocr_engine_label:
    ocr_engine = "local_hybrid"
else:
    ocr_engine = "auto"

ocr_speed_label = st.selectbox(
    "⚡ OCR 처리 속도",
    options=["균형(권장)", "정확도 우선", "고속(대량 캡처)"],
    index=0,
    help="대량 캡처에서는 고속 모드가 처리시간을 줄입니다. 정확도 우선은 시간이 더 걸릴 수 있습니다.",
)
if "정확도" in ocr_speed_label:
    ocr_speed_profile = "quality"
elif "고속" in ocr_speed_label:
    ocr_speed_profile = "fast"
else:
    ocr_speed_profile = "balanced"

with st.expander("🛟 429 우회: 캡처 텍스트 직접 붙여넣기", expanded=False):
    pasted_text = st.text_area(
        "탱크옥션/KB 화면에서 텍스트를 복사해 붙여넣으세요",
        height=180,
        placeholder="예: 경매 2024타경2979 ... 감정가격 796,000,000 ... 최저가격 509,440,000 ..."
    )
    if st.button("📝 붙여넣은 텍스트 바로 분석", key="parse_text_direct", use_container_width=True):
        if not pasted_text.strip():
            st.warning("텍스트를 먼저 붙여넣어 주세요.")
        else:
            text_df = parse_captured_text_to_dataframe(pasted_text, DEFAULT_COLUMNS)
            st.session_state.df = enrich_dataframe(text_df)
            st.session_state.uploaded_images = []
            st.success("✅ 텍스트 직접 분석이 완료되었습니다. 아래 대시보드에서 결과를 확인하세요.")

if uploaded_files:
    try:
        image_preview_files = [f for f in uploaded_files if is_image_upload(f)]
        preview_limit = 18
        preview_targets = image_preview_files[:preview_limit]

        st.markdown("#### 📸 업로드된 캡처본 품질 미리보기")
        if len(image_preview_files) > preview_limit:
            st.info(f"대량 업로드 감지: 전체 {len(image_preview_files)}장 중 앞 {preview_limit}장만 미리보기합니다. 분석은 전체 파일에 적용됩니다.")

        run_preview = st.checkbox(
            "품질 미리보기 실행",
            value=len(image_preview_files) <= 30,
            key="quality_preview_toggle",
            help="대량 업로드에서는 미리보기를 끄면 속도가 빨라집니다.",
        )
        if not run_preview:
            st.caption("미리보기를 생략하고 분석 속도를 우선합니다.")
        quality_cols = st.columns(max(1, min(3, max(1, len(preview_targets)))))
        for idx, uploaded_file in enumerate(preview_targets):
            if not run_preview:
                break
            if is_image_upload(uploaded_file):
                try:
                    quality = assess_image_quality(uploaded_file.getvalue())
                    with quality_cols[idx % len(quality_cols)]:
                        preview_image = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file
                        st.image(preview_image, use_container_width=True)
                        profile_name = {
                            "mobile_long": "긴 모바일 캡처",
                            "table_dense": "표 밀집 문서",
                            "mixed_ui": "혼합 화면",
                        }.get(str(quality.get("profile") or "mixed_ui"), "혼합 화면")
                        st.caption(
                            f"품질 점수: {quality.get('score', 50)} (기준 {quality.get('recommended_min_score', 64)}) "
                            f"/ 유형: {profile_name} / 캡처 보정 필요: {'예' if quality.get('needs_recapture') else '아니오'}"
                        )
                        st.write(build_recapture_guidance(quality))
                except Exception as preview_error:
                    st.warning(f"이미지 미리보기 중 오류가 발생했습니다: {uploaded_file.name} / {type(preview_error).__name__}")
    except Exception as preview_block_error:
        st.warning(
            "미리보기 블록에서 오류가 발생해 해당 단계를 건너뜁니다. "
            f"분석은 계속 진행 가능합니다. ({type(preview_block_error).__name__})"
        )

analyze_clicked = st.button("🚀 AI 심층 분석 시작", type="primary", use_container_width=True)

if analyze_clicked and not uploaded_files:
    st.warning("업로드된 파일이 없습니다. 캡처 이미지 또는 XLSX/CSV를 먼저 업로드해 주세요.")

elif analyze_clicked and uploaded_files:
    try:
        image_files = []
        excel_dfs = []

        st.session_state.processing_log = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.markdown("### 📊 처리 진행 상황")

        status_text.markdown("#### 1/4 파일 분류 중...")
        progress_bar.progress(25)
        time.sleep(0.5)

        for file in uploaded_files:
            try:
                file_ext = str(getattr(file, "name", "") or "").lower()
                if file_ext.endswith((".csv", ".xlsx")):
                    st.session_state.processing_log.append(f"✓ 엑셀 파일 감지: {file.name}")
                    df = pd.read_csv(file) if file_ext.endswith(".csv") else pd.read_excel(file)
                    excel_dfs.append(df)
                elif is_image_upload(file):
                    st.session_state.processing_log.append(f"✓ 이미지 파일 감지: {file.name}")
                    image_files.append(file)
                else:
                    st.session_state.processing_log.append(f"⚠️ 지원하지 않는 파일 형식: {file.name}")
            except Exception as file_error:
                st.session_state.processing_log.append(
                    f"✗ 파일 분류/로드 실패: {getattr(file, 'name', 'unknown')} ({type(file_error).__name__})"
                )

        if image_files:
            status_text.markdown(f"#### 2/4 Vision AI 분석 중... ({len(image_files)}개 이미지)")
            progress_bar.progress(50)

            if st.session_state.api_key or ocr_engine in {"auto", "local_hybrid"}:
                try:
                    if ocr_engine == "gemini":
                        st.session_state.processing_log.append("🤖 Google Gemini AI 시작...")
                    elif ocr_engine == "local_hybrid":
                        st.session_state.processing_log.append("🆓 로컬 무료 OCR(PaddleOCR+Tesseract) 시작...")
                    else:
                        st.session_state.processing_log.append("🤖/🆓 자동 엔진 선택 실행...")

                    vision_df = process_images_to_dataframe(
                        st.session_state.api_key,
                        image_files,
                        DEFAULT_COLUMNS,
                        mode=ocr_mode,
                        engine=ocr_engine,
                        speed_profile=ocr_speed_profile,
                    )
                    is_quota_hold = (
                        not vision_df.empty
                        and "사건번호" in vision_df.columns
                        and vision_df["사건번호"].astype(str).eq("AI쿼터대기").all()
                    )
                    if is_quota_hold:
                        st.warning("⚠️ Gemini 호출 한도(429)로 이미지 자동 판독이 일시 보류되었습니다. 1~2분 후 다시 시도해 주세요.")
                        st.session_state.processing_log.append("⚠️ API 호출 한도 초과 - 이미지 자동 판독 보류 데이터로 처리")
                    else:
                        st.session_state.processing_log.append(f"✓ AI 분석 완료: {len(vision_df)}건의 데이터 추출")
                        try:
                            quality_summary = summarize_extraction_quality(vision_df)
                            st.session_state.processing_log.append(
                                f"✓ OCR 복원 핵심필드 채움률: {quality_summary.get('core_fill_rate', 0):.1f}%"
                            )
                            fill_map = quality_summary.get("field_fill", {})
                            if fill_map:
                                st.caption(
                                    "핵심 필드 채움률: "
                                    + ", ".join([f"{k} {v:.0f}%" for k, v in fill_map.items()])
                                )
                        except Exception:
                            pass
                        try:
                            ocr_stats = dict(getattr(vision_df, "attrs", {}).get("ocr_stats") or {})
                            if ocr_stats:
                                st.info(
                                    "고속 처리 통계: "
                                    f"속도모드={ocr_stats.get('speed_profile', '-')}, "
                                    f"평균처리={ocr_stats.get('avg_ms_per_image', 0):.0f}ms/장, "
                                    f"처리량={ocr_stats.get('images_per_minute', 0):.1f}장/분, "
                                    f"재시도율={ocr_stats.get('tesseract_retry_rate', 0.0):.1f}%, "
                                    f"재시도실사용율={ocr_stats.get('tesseract_used_rate', 0.0):.1f}%"
                                )
                                st.session_state.processing_log.append(
                                    "✓ OCR 런타임 통계 "
                                    f"(avg_ms={ocr_stats.get('avg_ms_per_image', 0):.0f}, "
                                    f"throughput={ocr_stats.get('images_per_minute', 0):.1f}/min, "
                                    f"retry_rate={ocr_stats.get('tesseract_retry_rate', 0.0):.1f}%, "
                                    f"used_rate={ocr_stats.get('tesseract_used_rate', 0.0):.1f}%)"
                                )
                        except Exception:
                            pass
                    excel_dfs.append(vision_df)
                except Exception as e:
                    st.error("❌ AI 분석 오류: AI 호출이 일시 실패했습니다. 잠시 후 다시 시도하거나 CSV/XLSX 업로드로 진행해 주세요.")
                    st.caption(f"상세: {str(e)[:220]}")
                    st.session_state.processing_log.append(f"✗ AI 오류: {str(e)}")
            else:
                st.warning("⚠️ Gemini 모드에서는 API 키가 필요합니다")
                st.session_state.processing_log.append("⚠️ Gemini 모드 + API 키 미입력 - 이미지 분석 생략")
                if not excel_dfs:
                    st.info("Gemini API 키를 입력하거나 OCR 엔진을 '로컬 무료' 또는 '자동'으로 변경해 주세요.")

        status_text.markdown("#### 3/4 데이터 통합 및 심사...")
        progress_bar.progress(75)
        time.sleep(0.3)

        if excel_dfs:
            combined_df = pd.concat(excel_dfs, ignore_index=True)
            st.session_state.processing_log.append(f"✓ 총 {len(combined_df)}건 데이터 통합")

            enriched_df = enrich_dataframe(combined_df)
            st.session_state.df = enriched_df
            st.session_state.processing_log.append("✓ 심사 로직 적용 완료")

            status_text.markdown("#### 4/4 적격 자산 이미지 보관...")
            progress_bar.progress(90)

            approved_df = enriched_df[status_mask(enriched_df)]
            approved_filenames = approved_df["원본파일명"].astype(str).tolist()

            temp_approved_images = [img for img in image_files if img.name in approved_filenames]
            st.session_state.uploaded_images = temp_approved_images
            st.session_state.processing_log.append(f"✓ 적격 {len(temp_approved_images)}건 이미지 보관")
            st.session_state.processing_log.append(f"✓ 부적격 {len(image_files) - len(temp_approved_images)}건 이미지 자동 삭제")

            progress_bar.progress(100)
            status_text.markdown("#### ✅ 분석 완료!")
            time.sleep(0.5)

            st.success("🎉 심층 평가 완료! 스크롤을 내려 결과를 확인하세요")

            with st.expander("📋 상세 처리 로그 보기"):
                for log in st.session_state.processing_log:
                    st.text(log)

            if not st.session_state.df.empty:
                st.markdown("### 🧠 자동 정리 결과")
                st.caption("캡처본에서 추출된 핵심 사실이 권리분석과 대응 브리핑으로 이어지는 흐름을 바로 확인할 수 있습니다.")
                for _, row in st.session_state.df.head(3).iterrows():
                    summary = build_structured_case_summary(row.to_dict())
                    with st.container():
                        st.markdown(f"#### 📌 {row.get('사건번호','미상')}")
                        st.write(summary["자동정리요약"])
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.info(f"정리상태: {summary['정리상태']} / 완성도: {summary['완성도']}%")
                        with col_b:
                            st.success(f"보완 필요 필드: {', '.join(summary.get('누락필드', [])) or '없음'}")
                        st.write(build_case_briefing(row.to_dict()))
                        st.divider()
        else:
            progress_bar.progress(100)
            status_text.markdown("#### ⚠️ 처리할 데이터가 없습니다")
            st.warning("처리할 데이터가 생성되지 않았습니다. API 키/업로드 파일 형식/파일 내용을 확인해 주세요.")

    except Exception as pipeline_error:
        st.error(
            "❌ 분석 파이프라인에서 오류가 발생했습니다. "
            "텍스트 직접 분석 또는 CSV/XLSX 업로드 모드로 우선 진행해 주세요."
        )
        st.caption(f"오류 유형: {type(pipeline_error).__name__}")

df = st.session_state.df

# =========================================================================
# SECTION 2: 대시보드
# =========================================================================
st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📈 권리분석 및 사건 판단 대시보드</div>", unsafe_allow_html=True)

if not df.empty:
    mask_approved = status_mask(df)
    approved = df[mask_approved]
    rejected = df[~mask_approved]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class='metric-box'>
            <div class='metric-title'>📊 Total Assets</div>
            <div class='metric-value'>{len(df)}</div>
            <div style='font-size:14px; color:#94a3b8; margin-top:10px;'>스캔된 전체 자산</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class='metric-box'>
            <div class='metric-title' style='color:#22c55e;'>✅ Approved</div>
            <div class='metric-value' style='background:linear-gradient(135deg, #22c55e 0%, #16a34a 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent;'>{len(approved)}</div>
            <div style='font-size:14px; color:#94a3b8; margin-top:10px;'>우선 검토 적격</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class='metric-box'>
            <div class='metric-title' style='color:#ef4444;'>❌ Rejected</div>
            <div class='metric-value' style='background:linear-gradient(135deg, #ef4444 0%, #dc2626 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent;'>{len(rejected)}</div>
            <div style='font-size:14px; color:#94a3b8; margin-top:10px;'>리스크 초과/보류</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        if not df.empty:
            ltv_series = pd.to_numeric(df["추정LTV"].astype(str).str.replace("%", "", regex=False), errors="coerce")
            avg_ltv = float(ltv_series.fillna(0).mean())
        else:
            avg_ltv = 0
        ltv_color = "#22c55e" if avg_ltv < 75 else "#f59e0b" if avg_ltv < 85 else "#ef4444"
        st.markdown(f"""
        <div class='metric-box'>
            <div class='metric-title'>📊 Average LTV</div>
            <div class='metric-value' style='background:linear-gradient(135deg, {ltv_color} 0%, {ltv_color} 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent;'>{avg_ltv:.1f}%</div>
            <div style='font-size:14px; color:#94a3b8; margin-top:10px;'>포트폴리오 평균</div>
        </div>
        """, unsafe_allow_html=True)
    
    with st.expander("🧩 규칙 실행 카드 보기", expanded=True):
        render_rule_execution_cards(df, max_cards=8)

    # 컴플라이언스 경고
    if "열람필수" in df["등기부열람여부"].values:
        st.markdown("""
        <div class='warning-box'>
            <strong style='font-size:20px;'>⚠️ 컴플라이언스 경고</strong><br>
            해당 물건 중 <strong>가처분/가등기 등 특수 권리 하자</strong>가 존재하는 자산이 발견되었습니다.<br>
            반드시 <strong>실물 등기부등본을 교차 검증</strong>하십시오.
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    
    # ============ 적격 자산 표시 ============
    st.markdown("<h2 style='color:#22c55e; font-weight:900; margin:40px 0 30px 0;'>🟢 우선 검토 적격 사건 (Priority Review)</h2>", unsafe_allow_html=True)
    
    if not approved.empty:
        for _, row in approved.iterrows():
            debt_fmt = f"{_safe_float(row.get('부채총액',0)):,.0f}원"
            val_fmt = f"{_safe_float(row.get('감정가',0)):,.0f}원"
            days_left = f"<span style='color:#ef4444; font-weight:900;'>D-{int(row.get('잔여일수', 0))}</span>" if row.get("잔여일수") != "" else ""
            
            # 채권자 조언
            creditor_name = str(row.get('주요채권자', ''))
            creditor_advice = get_creditor_advice(creditor_name) if creditor_name else ""
            
            st.markdown(f"""
            <div class="card-passed">
                <h3 style='font-size:28px; font-weight:900; color:#1e293b; margin-bottom:20px;'>
                    📋 사건번호: {row.get('사건번호', 'N/A')}
                </h3>
                <p style='font-size:18px; color:#64748b; margin-bottom:30px;'>
                    🏠 {row.get('아파트명', '주소 미상')} | 📍 {row.get('주소', '')}
                </p>
                
                <div class='info-grid'>
                    <div class='info-item'>
                        <div class='info-label'>Scoring & Grade</div>
                        <div class='info-data'>{row['분석점수']}점 ({row['분석등급']}등급)</div>
                    </div>
                    <div class='info-item'>
                        <div class='info-label'>매각기일</div>
                        <div class='info-data'>{row.get('매각기일','')} {days_left}</div>
                    </div>
                    <div class='info-item'>
                        <div class='info-label'>LTV (부채비율)</div>
                        <div class='info-data' style='color:#3b82f6;'>{row['추정LTV']}</div>
                    </div>
                    <div class='info-item'>
                        <div class='info-label'>부채 / 감정가</div>
                        <div class='info-data' style='font-size:16px;'>{debt_fmt}<br>{val_fmt}</div>
                    </div>
                </div>
                
                <div style='background:#f8fafc; padding:25px; border-radius:12px; margin:25px 0;'>
                    <p style='font-size:18px; margin:10px 0;'>
                        <strong style='color:#3b82f6;'>🎯 판단 포인트:</strong><br>
                        <span style='font-size:16px;'>{row['제안포인트']}</span>
                    </p>
                    <p style='font-size:18px; margin:10px 0;'>
                        <strong style='color:#f59e0b;'>⚖️ 권리 리스크:</strong><br>
                        <span style='font-size:16px;'>{row['권리요약']}</span>
                    </p>
                    <p style='font-size:18px; margin:10px 0;'>
                        <strong style='color:#8b5cf6;'>📌 주요 채권자/권리 정보:</strong><br>
                        <span style='font-size:16px;'>{creditor_name or '미상'}</span>
                    </p>
                    {"<p style='font-size:15px; margin:15px 0 0 0; padding:15px; background:#fef3c7; border-radius:8px; color:#78350f;'><strong>💡 채권자 대응 전략:</strong><br>" + creditor_advice + "</p>" if creditor_advice else ""}
                </div>
                
                <div class="expert-analysis-box">
                    <strong style='font-size:18px;'>🧠 AI 종합 의견:</strong><br>
                    <p style='margin-top:15px; line-height:1.8;'>{row.get('AI_심층분석','생성된 의견이 없습니다.')}</p>
                </div>
                
                <div style='margin-top:25px; padding:20px; background:#eff6ff; border-radius:12px;'>
                    <strong style='color:#1e40af; font-size:16px;'>📝 실무 메모:</strong><br>
                    <p style='margin-top:10px; font-size:15px; color:#1e293b;'>{row['담당자메모']}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("📭 현재 분석된 대상 중 권리분석 기준을 충족한 사건이 없습니다.")
    
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    
    # ============ 부적격 자산 표시 ============
    st.markdown("<h2 style='color:#ef4444; font-weight:900; margin:40px 0 30px 0;'>🔴 수익성 미달 및 보류 자산 (Rejected or Failed)</h2>", unsafe_allow_html=True)
    
    if not rejected.empty:
        for _, row in rejected.iterrows():
            debt_fmt = f"{_safe_float(row.get('부채총액',0)):,.0f}원"
            val_fmt = f"{_safe_float(row.get('감정가',0)):,.0f}원"
            
            st.markdown(f"""
            <div class="card-failed">
                <h3 style='font-size:24px; font-weight:900; color:#1e293b;'>
                    📋 사건번호: {row.get('사건번호', '판독불가')}
                </h3>
                <p style='color: #ef4444; font-weight:900; font-size: 20px; margin: 20px 0; padding:15px; background:#fef2f2; border-radius:8px;'>
                    ⛔ 차단 사유: {row['심사상태']}
                </p>
                
                <div class='info-grid'>
                    <div class='info-item'>
                        <div class='info-label'>추정 LTV</div>
                        <div class='info-data' style='color:#ef4444;'>{row['추정LTV']}</div>
                    </div>
                    <div class='info-item'>
                        <div class='info-label'>총 부채</div>
                        <div class='info-data' style='font-size:16px;'>{debt_fmt}</div>
                    </div>
                    <div class='info-item'>
                        <div class='info-label'>감정가</div>
                        <div class='info-data' style='font-size:16px;'>{val_fmt}</div>
                    </div>
                    <div class='info-item'>
                        <div class='info-label'>권리요약</div>
                        <div class='info-data' style='font-size:14px;'>{row['권리요약']}</div>
                    </div>
                </div>
                
                <div style='margin-top: 20px; padding:20px; background:#fef2f2; border-radius:12px;'>
                    <strong style='color:#991b1b;'>📝 AI 코멘트:</strong><br>
                    <p style='margin-top:10px; font-size:15px; color:#7f1d1d;'>{row.get('AI_심층분석','')}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("✅ 부적격 또는 판독 제한으로 보류된 자산이 없습니다.")

else:
    st.info("📤 데이터 소스를 업로드하여 자산 평가를 시작하십시오.")

# =========================================================================
# SECTION 3: 데이터 보관함
# =========================================================================
st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📦 전체 데이터보관 및 캡처 관리</div>", unsafe_allow_html=True)

if not df.empty:
    mask_approved = status_mask(df)
    approved_df = df[mask_approved]
    rejected_df = df[~mask_approved]
    
    tab1, tab2 = st.tabs(["🟢 적격 데이터", "🔴 부적격 데이터"])
    
    with tab1:
        st.markdown("### ✅ 적격 (Approved) 텍스트 데이터")
        if not approved_df.empty:
            st.dataframe(
                approved_df.drop(columns=["원본파일명"], errors="ignore"), 
                use_container_width=True,
                height=400
            )
        else:
            st.info("적격 통과된 텍스트 데이터가 없습니다.")
        
        st.markdown("### 📷 권리분석/보관 대상 캡처본")
        if st.session_state.uploaded_images:
            cols = st.columns(3)
            for i, img in enumerate(st.session_state.uploaded_images):
                with cols[i % 3]:
                    st.image(img, caption=f"✅ {img.name}", use_container_width=True)
                    if st.button("🗑️ 영구 삭제", key=f"del_{i}", use_container_width=True):
                        st.session_state.uploaded_images = [x for x in st.session_state.uploaded_images if x.name != img.name]
                        st.rerun()
        else:
            st.info("보관 중인 캡처본이 없습니다.")
    
    with tab2:
        st.markdown("### ❌ 부적격/보류 (Rejected) 텍스트 데이터")
        st.caption("⚠️ 부적격 자산의 캡처본 이미지는 데이터 최적화를 위해 AI 심사 직후 서버에서 즉시 영구 삭제되었습니다.")
        if not rejected_df.empty:
            st.dataframe(
                rejected_df.drop(columns=["원본파일명"], errors="ignore"), 
                use_container_width=True,
                height=400
            )
        else:
            st.info("부적격으로 분류된 데이터가 없습니다.")
else:
    st.info("보관된 데이터가 없습니다.")

# =========================================================================
# SECTION 4: 리포트 출력
# =========================================================================
st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📄 보고서 및 대응 브리핑 출력</div>", unsafe_allow_html=True)

if not df.empty:
    approved_df = df[status_mask(df)]
    if not approved_df.empty:
        st.markdown("#### 💼 의사결정용 전문 리포트 생성")
        st.caption("적격으로 분류된 물건만 보고서로 출력되며, 자동 정리 요약과 보완 필요 필드도 함께 포함됩니다.")
        
        export_rows = approved_df.head(50).to_dict(orient="records")
        ppt_bytes = generate_pptx_bytes(export_rows)
        pdf_bytes = generate_pdf_bytes(export_rows)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📄 PDF 심사보고서",
                data=pdf_bytes,
                file_name="NPL_Underwriting_Report_Approved.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📊 PPTX 브리핑 덱",
                data=ppt_bytes,
                file_name="Case_Briefing_Approved.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True
            )
    else:
        st.warning("출력 가능한 '적격(Approved)' 자산 데이터가 없습니다.")
else:
    st.info("데이터가 없습니다.")

# =========================================================================
# SECTION 5: 사건 분석 및 대응 전략 가이드
# =========================================================================
st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📚 사건 분석 및 협상 전략 센터</div>", unsafe_allow_html=True)

with st.expander("1️⃣ [선별] 유망 사건 선별 기준", expanded=False):
    st.markdown("""
    <div style="font-size:16px; line-height:1.8; padding:20px;">
    <h3 style='color:#1e293b; font-weight:900;'>사건 분석의 핵심 기준</h3>
    <p>업무 리소스를 효율적으로 배분하고, 실제 검토 가치가 높은 사건만 대시보드에 <span style='background:#dcfce7; padding:2px 8px; border-radius:4px; font-weight:700;'>우선 검토</span>로 정리합니다.</p>
    
    <h4 style='color:#ef4444; font-weight:900; margin-top:30px;'>📌 영업에서 즉시 제외되는 건 (적색 경보)</h4>
    <ol style='line-height:2;'>
        <li><strong>시간적 여유 (매각기일 30일 이상)</strong><br>심리적 무장해제가 덜 되어 고금리 방어선을 치려 함. 절박함이 없어 접근 금지.</li>
        <li><strong>여유 자금 가능 (LTV 55% 이하)</strong><br>시중은행으로도 자력 해결 가능하므로 대부업 유입 확률 0%. 시간 낭비.</li>
        <li><strong>극단적 부실 (LTV 85% 초과)</strong><br>권리·자금 구조가 매우 불안정해 실무적으로 판단이 어려운 사건으로 보입니다.</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)

with st.expander("2️⃣ [협상] 채권자/권리 대응 기준", expanded=False):
    st.markdown("""
    <div style='padding:20px;'>
        <h3 style='color:#1e293b; font-weight:900; margin-bottom:25px;'>🤝 채권자/협상 대응 가이드</h3>
        <p style='font-size:16px; margin-bottom:30px;'>시스템이 권리 상황과 채권자 성향을 분석해, 실무적으로 어떤 방식으로 접근해야 하는지 정리합니다.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # A타입 - 저축은행
    st.markdown("""
    <div class='lender-card' style='border-left-color:#22c55e;'>
        <div class='lender-name'>🟢 기준 A: 안정적 사건 유형</div>
        <div style='background:#f0fdf4; padding:20px; border-radius:12px; margin:15px 0;'>
            <p class='lender-contact'><strong>👤 담당자:</strong> 김영희 팀장</p>
            <p class='lender-contact'><strong>📞 직통:</strong> 02-3456-7890</p>
            <p class='lender-contact'><strong>📱 휴대폰:</strong> 010-1234-5678</p>
            <p class='lender-contact'><strong>📧 이메일:</strong> younghee.kim@sbbank.co.kr</p>
            <p class='lender-contact'><strong>🏢 소속:</strong> SB저축은행 부동산금융본부</p>
        </div>
        <div style='padding:15px; background:#fef3c7; border-radius:8px; margin:15px 0;'>
            <strong style='color:#78350f;'>📋 수용 조건:</strong>
            <ul style='margin:10px 0; padding-left:20px; color:#78350f;'>
                <li>LTV 55~80% 사이 (절대 한도)</li>
                <li>선순위 권리 완벽 (근저당, 가압류 없음)</li>
                <li>금리 연 6~9% (가장 저렴)</li>
                <li>최저 대출액 2억 이상</li>
                <li>심사기간 5영업일</li>
            </ul>
        </div>
        <p style='font-size:14px; color:#64748b; margin-top:15px;'>
            ⭐ 평가: 가장 저렴하나 심사가 엄격함. 깨끗한 물건만 가능.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # B타입 - 대부업체
    st.markdown("""
    <div class='lender-card' style='border-left-color:#3b82f6;'>
        <div class='lender-name'>🔵 기준 B: 보완이 필요한 사건 유형</div>
        <div style='background:#eff6ff; padding:20px; border-radius:12px; margin:15px 0;'>
            <p class='lender-contact'><strong>👤 담당자:</strong> 박철수 이사</p>
            <p class='lender-contact'><strong>📞 직통:</strong> 02-8765-4321</p>
            <p class='lender-contact'><strong>📱 휴대폰:</strong> 010-9876-5432</p>
            <p class='lender-contact'><strong>📧 이메일:</strong> cs.park@primecapital.kr</p>
            <p class='lender-contact'><strong>🏢 소속:</strong> 프라임캐피탈 특수자산팀</p>
        </div>
        <div style='padding:15px; background:#fef3c7; border-radius:8px; margin:15px 0;'>
            <strong style='color:#78350f;'>📋 수용 조건:</strong>
            <ul style='margin:10px 0; padding-left:20px; color:#78350f;'>
                <li>LTV 80~85% (높은 레버리지)</li>
                <li>가압류 등 일부 하자 수용 가능</li>
                <li>금리 연 12~18%</li>
                <li>매각 가치만 나오면 2일 내 승인</li>
                <li>최소 대출액 1억</li>
            </ul>
        </div>
        <p style='font-size:14px; color:#64748b; margin-top:15px;'>
            ⭐ 평가: 매각 방어(시간 벌기)가 시급한 소유주에게 즉효. 속도가 생명.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # C타입 - NPL 전문
    st.markdown("""
    <div class='lender-card' style='border-left-color:#ef4444;'>
        <div class='lender-name'>🔴 기준 C: 고위험 사건 유형</div>
        <div style='background:#fef2f2; padding:20px; border-radius:12px; margin:15px 0;'>
            <p class='lender-contact'><strong>👤 담당자:</strong> 최민준 대표</p>
            <p class='lender-contact'><strong>📞 직통:</strong> 02-5555-8888</p>
            <p class='lender-contact'><strong>📱 휴대폰:</strong> 010-5555-8888</p>
            <p class='lender-contact'><strong>📧 이메일:</strong> minjun.choi@nplasset.com</p>
            <p class='lender-contact'><strong>🏢 소속:</strong> NPL자산관리 대표이사</p>
        </div>
        <div style='padding:15px; background:#fef3c7; border-radius:8px; margin:15px 0;'>
            <strong style='color:#78350f;'>📋 수용 조건:</strong>
            <ul style='margin:10px 0; padding-left:20px; color:#78350f;'>
                <li>LTV 무관 (85% 초과도 검토)</li>
                <li>가처분, 가등기 등 복잡한 권리도 수용</li>
                <li>금리 연 18~24% (고위험 고수익)</li>
                <li>명도 이슈 있어도 가능</li>
                <li>최소 대출액 5천만원</li>
            </ul>
        </div>
        <p style='font-size:14px; color:#64748b; margin-top:15px;'>
            ⭐ 평가: 다른 곳에서 거절당한 최악의 물건도 검토. 최후의 수단.
        </p>
    </div>
    """, unsafe_allow_html=True)

with st.expander("3️⃣ [협상술] 채권단 설득 및 헤어컷(탕감) 전술", expanded=False):
    st.markdown("""
    <div style="font-size:16px; line-height:1.8; padding:20px;">
    <h3 style='color:#1e293b; font-weight:900;'>채권자 유형별 대응 전략</h3>
    
    <div style='background:#eff6ff; padding:20px; border-radius:12px; margin:20px 0;'>
        <h4 style='color:#1e40af; font-weight:900;'>🏛️ 유동화/NPL 펀드</h4>
        <p><strong>성향:</strong> 신속한 현금회수 선호</p>
        <p><strong>전략:</strong> "일시불 지급할 테니 이자 및 유동화 할인율만큼 헤어컷(원금 감면) 해달라" 요구</p>
        <p><strong>효과:</strong> 매우 높음 (80% 이상 협상 성공률)</p>
    </div>
    
    <div style='background:#fef3c7; padding:20px; border-radius:12px; margin:20px 0;'>
        <h4 style='color:#78350f; font-weight:900;'>🏦 1/2금융권</h4>
        <p><strong>성향:</strong> 보수적, 숫자 중시</p>
        <p><strong>전략:</strong> "유찰 시 배당액 손실 시뮬레이션(숫자)"을 제시 → 배당 의존보다 현 대환수용이 안전함을 설득</p>
        <p><strong>효과:</strong> 중간 (50% 정도)</p>
    </div>
    
    <div style='background:#fef2f2; padding:20px; border-radius:12px; margin:20px 0;'>
        <h4 style='color:#991b1b; font-weight:900;'>🏢 공공/조세채권</h4>
        <p><strong>성향:</strong> 단호함, 법적 절차 준수</p>
        <p><strong>전략:</strong> 선순위 압류는 분할납부 및 한시적 압류 해제를 통한 대환으로 우선 처리</p>
        <p><strong>효과:</strong> 낮음 (협상 여지 거의 없음)</p>
    </div>
    </div>
    """, unsafe_allow_html=True)

# =========================================================================
# 푸터
# =========================================================================
st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='text-align:center; padding:40px 20px; color:#94a3b8; font-size:14px;'>
    <p style='font-weight:700; font-size:16px; margin-bottom:10px;'>© 2026 Auctiscope</p>
    <p>Powered by Google Gemini AI | Built with Streamlit</p>
    <p style='margin-top:20px; font-size:13px;'>이 시스템은 전문가용 의사결정 보조 도구입니다. 최종 판단은 반드시 실물 등기부와 현장 실사를 통해 검증하십시오.</p>
</div>
""", unsafe_allow_html=True)
