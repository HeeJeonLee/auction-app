import pandas as pd
import streamlit as st
from pathlib import Path
from io import BytesIO
from report_generator import generate_pptx_bytes, generate_pdf_bytes

from analysis import (
    calculate_candidate_score, classify_grade, recommend_lender, 
    build_rights_summary, suggest_candidate_flag, build_owner_pitch, 
    build_visit_advice, build_phone_pitch, build_visit_pitch,
    passes_market_filters, needs_registry_verification
)

# 모바일 환경에 최적화된 설정 (centered layout, sidebar collapsed)
st.set_page_config(page_title="핸드폰 캡쳐로 성적표(50억까지)", page_icon="📱", layout="centered", initial_sidebar_state="collapsed")

# 모바일 UI 스타일 주입
st.markdown("""
<style>
    .stButton>button, .stDownloadButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3.5rem;
        font-weight: bold;
        font-size: 1.1rem;
        margin-bottom: 0.5rem;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 1.5rem;
        padding-left: 1rem;
        padding-right: 1rem;
        padding-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("📱 경매취하 AI 매칭시스템")
st.caption("스마트폰 전용 버전에 맞추어 최적화되었습니다. 5억~50억 물건의 승인 가능성을 자동으로 진단합니다.")

# 모바일 가독성을 위해 expander로 안내문구 숨김/표시
with st.expander("📌 사용 안내 (클릭하여 열기)"):
    st.markdown("""
    1. **데이터 업로드**: 폰에 저장된 시트(Excel/CSV)를 업로드하세요.
    2. **자동 분석**: LTV 한도, 대부업체 추천, 채권자협상 가이드가 자동으로 매칭됩니다.
    3. **내려받기**: 결과 리포트(PPT, PDF)를 다운로드해 모바일로 즉시 보고 가능합니다.
    """)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_COLUMNS = [
    "사건번호", "법원명", "물건번호", "주소", "아파트명", "감정가", "최저매각가격", "낙찰예상가",
    "부채총액", "청산가능여부", "청산가능비율", "근저당여부", "근저당금액", "압류여부",
    "가압류여부", "가처분여부", "임차권등기여부", "전세권여부", "가등기여부", "등기부열람여부",
    "권리요약", "분석점수", "분석등급", "후보여부", "추천대주", "담당자메모",
    "KB시세", "결제요청", "주요채권자"
]

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame(columns=DEFAULT_COLUMNS)

def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in DEFAULT_COLUMNS:
        if col not in result.columns:
            result[col] = ""
    result = result[DEFAULT_COLUMNS]

    if "분석점수" not in result.columns: result["분석점수"] = ""
    if "분석등급" not in result.columns: result["분석등급"] = ""

    _drop_indices: list[int] = []

    for idx, row in result.iterrows():
        row_dict = row.to_dict()
        score = calculate_candidate_score(row_dict)
        grade = classify_grade(score)
        
        result.at[idx, "분석점수"] = score
        result.at[idx, "분석등급"] = grade
        
        if not str(row.get("권리요약") or "").strip():
            result.at[idx, "권리요약"] = build_rights_summary(row_dict)
            
        row_dict_updated = result.loc[idx].to_dict()
        
        if not str(row.get("추천대주") or "").strip():
            result.at[idx, "추천대주"] = recommend_lender(row_dict_updated)

        try:
            market_ok = passes_market_filters(row_dict_updated)
        except Exception:
            market_ok = False

        if not market_ok:
            _drop_indices.append(idx)
            continue

        if not str(row.get("후보여부") or "").strip():
            result.at[idx, "후보여부"] = suggest_candidate_flag(row_dict_updated)

        try:
            if needs_registry_verification(row_dict_updated):
                result.at[idx, "등기부열람여부"] = result.at[idx, "등기부열람여부"] or "요청"
        except Exception:
            pass

        if not str(row.get("담당자메모") or "").strip():
            result.at[idx, "담당자메모"] = f"진단 요약:\n- {build_owner_pitch(row_dict_updated)}\n- {build_visit_advice(row_dict_updated)}"

    if _drop_indices:
        result = result.drop(index=_drop_indices).reset_index(drop=True)

    return result

st.subheader("📂 1. 데이터 업로드")
uploaded_file = st.file_uploader("엑셀/CSV 파일 선택", type=["xlsx", "xls", "csv"], label_visibility="collapsed")

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        st.session_state.df = enrich_dataframe(df)
        st.success("✅ 파일 업로드 및 자동 분석이 완료되었습니다!")
    except Exception as e:
        st.error(f"❌ 파일 읽기 실패: {e}")

# 모바일용 샘플 템플릿 다운로드 버튼
buf = BytesIO()
pd.DataFrame(columns=DEFAULT_COLUMNS).to_excel(buf, index=False, engine="openpyxl")
buf.seek(0)
st.download_button(
    label="⬇️ 빈 양식 시트 다운로드",
    data=buf.getvalue(),
    file_name="auction_template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

st.markdown("---")

# 탭을 활용하여 모바일에서 화면을 쓸어넘기는 듯한 UI 구성
tab1, tab2 = st.tabs(["📊 분석 요약 및 출력", "🔍 전체 데이터 검토"])

with tab1:
    st.subheader("📊 2. 후보 분석 리포트")
    if not st.session_state.df.empty:
        summary_df = enrich_dataframe(st.session_state.df)
        count = len(summary_df)
        candidate_count = (summary_df["후보여부"].astype(str).str.contains("Y|✔️|O", case=False, na=False)).sum()
        avg_score = round(summary_df["분석점수"].astype(float).mean(), 1) if not summary_df["분석점수"].empty else 0
        
        # 메트릭 컴포넌트를 이용해 모바일에서 직관적으로 수치 제공
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("통과 건수", f"{count}건")
        col_m2.metric("후보 선정", f"{candidate_count}건")
        col_m3.metric("평균 점수", f"{avg_score}점")
        
        st.markdown("### 🏆 최상위 매칭 미리보기 (Top 2)")
        for _, row in summary_df.head(2).iterrows():
            with st.container():
                st.info(f"**{row.get('아파트명') or '아파트명 미입력'}** (총점 {row.get('분석점수')} / 등급 {row.get('분석등급')})")
                st.caption(f"**매칭 대주**: {row.get('추천대주')}")
                st.caption(f"**요약**: {row.get('담당자메모')}")

        st.markdown("### 📥 3. 휴대폰으로 리포트 내보내기")
        export_rows = summary_df.head(10).to_dict(orient="records")
        ppt_bytes = generate_pptx_bytes(export_rows)
        pdf_bytes = generate_pdf_bytes(export_rows)

        st.download_button(
            label="📄 PDF 리포트 다운로드", 
            data=pdf_bytes, 
            file_name="report_top10.pdf", 
            mime="application/pdf",
            use_container_width=True
        )
        st.download_button(
            label="📊 PPTX 프레젠테이션 다운로드", 
            data=ppt_bytes, 
            file_name="report_top10.pptx", 
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True
        )
    else:
        st.warning("데이터가 없습니다. 파일을 업로드해주세요.")

with tab2:
    st.subheader("🔍 전체 데이터베이스")
    if not st.session_state.df.empty:
        st.caption("좌우로 스와이프하여 데이터를 확인하세요.")
        edited_df = st.data_editor(st.session_state.df, use_container_width=True, hide_index=True)
        
        if st.button("🔄 수정된 내용 재분석", use_container_width=True):
            st.session_state.df = enrich_dataframe(edited_df)
            st.success("데이터가 재분석되었습니다.")
            st.rerun()
            
        if st.button("🗑️ 초기화(비우기)", use_container_width=True):
            st.session_state.df = pd.DataFrame(columns=DEFAULT_COLUMNS)
            st.rerun()
    else:
        st.write("표시할 데이터가 없습니다.")

