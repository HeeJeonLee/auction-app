import pandas as pd
import streamlit as st
from pathlib import Path
from io import BytesIO
from report_generator import generate_pptx_bytes, generate_pdf_bytes

from analysis import (
    calculate_candidate_score, classify_grade, recommend_lender, 
    build_rights_summary, suggest_candidate_flag, build_owner_pitch, 
    build_visit_advice, build_phone_pitch, build_visit_pitch,
    passes_market_filters, needs_registry_verification, _safe_float
)
from vision_extractor import process_images_to_dataframe

st.set_page_config(page_title="NPL Underwriting Pro", page_icon="🏢", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
        background-color: #f7f9fc;
        color: #2c3e50;
    }
    
    /* 대형 섹션 헤더 (고급/전문가 느낌) */
    .section-title {
        font-size: 28px;
        font-weight: 900;
        color: #1a252f;
        margin-top: 50px;
        margin-bottom: 20px;
        border-bottom: 3px solid #34495e;
        padding-bottom: 10px;
    }

    .metric-box {
        background-color: #ffffff;
        padding: 25px;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.04);
        border-top: 5px solid #2980b9;
        text-align: left;
        margin-bottom: 20px;
    }
    .metric-value { font-size: 32px; font-weight: 900; color: #2980b9; margin: 10px 0; }
    .metric-title { font-size: 16px; font-weight: 700; color: #7f8c8d; }
    
    .card-passed { 
        background: #ffffff;
        padding: 30px; 
        border-radius: 12px; 
        margin-bottom: 25px; 
        border: 1px solid #e1e8ed;
        border-left: 8px solid #27ae60;
        box-shadow: 0 6px 20px rgba(0,0,0,0.05); 
    }
    .card-failed { 
        background: #ffffff;
        padding: 30px; 
        border-radius: 12px; 
        margin-bottom: 25px; 
        border: 1px solid #e1e8ed;
        border-left: 8px solid #c0392b;
        box-shadow: 0 6px 20px rgba(0,0,0,0.05); 
    }
    
    .expert-analysis-box {
        background-color: #fdfbf7;
        border-left: 5px solid #f39c12;
        padding: 20px;
        margin-top: 20px;
        font-size: 16px;
        line-height: 1.7;
        color: #2c3e50;
    }

    .info-label { font-size: 15px; color: #7f8c8d; margin-bottom: 5px; }
    .info-data { font-size: 18px; font-weight: 700; color: #2c3e50; }

    .badge-approved { background: #eafaf1; color: #27ae60; padding: 6px 12px; border-radius: 6px; font-size: 14px; font-weight: 900; }
    .badge-rejected { background: #fdedec; color: #c0392b; padding: 6px 12px; border-radius: 6px; font-size: 14px; font-weight: 900; }
    
    .stDownloadButton>button { width: 100%; border-radius: 8px; font-weight: bold; background-color: #2c3e50; color: white; border: none; height: 50px; font-size: 16px;}
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='font-size: 36px; font-weight: 900; color: #2c3e50;'>🏢 NPL / 매입 타당성 심사 시스템 (Underwriting Pro)</div>", unsafe_allow_html=True)
st.caption("대주(Lender) 파이낸싱 및 특수 물건 매입 타당성을 검증하는 최상위 전문가용 Risk Assessment Dashboard")

DEFAULT_COLUMNS = [
    "원본파일명", "사건번호", "매각기일", "잔여일수", "법원명", "물건번호", "주소", "아파트명", "감정가", "최저매각가격", "낙찰예상가",
    "부채총액", "청산가능여부", "권리요약", "분석점수", "분석등급", "추천대주", "담당자메모",
    "KB시세", "주요채권자", "심사상태", "추정LTV", "AI_심층분석", "등기부열람여부", "근저당여부", "압류여부", "가처분여부"
]

if "df" not in st.session_state: st.session_state.df = pd.DataFrame(columns=DEFAULT_COLUMNS)
if "uploaded_images" not in st.session_state: st.session_state.uploaded_images = []
if "approved_image_info" not in st.session_state: st.session_state.approved_image_info = {}

# Require 1: API Key Persistence using Session State and Secrets
if "api_key" not in st.session_state:
    try:
        st.session_state.api_key = st.secrets.get("GEMINI_API_KEY", "")
    except:
        st.session_state.api_key = ""

def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in DEFAULT_COLUMNS:
        if col not in result.columns: result[col] = ""
            
    for idx, row in result.iterrows():
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
        
        if not str(row.get("추천대주") or "").strip():
            result.at[idx, "추천대주"] = recommend_lender(row_dict_updated)

        try:
            market_ok = passes_market_filters(row_dict_updated)
        except Exception:
            market_ok = False

        status_msg = "부적격 (Rejected)"
        if not market_ok:
            status_msg = "부적격 (LTV 85% 한도 초과 또는 치명적 악성 권리)"
        else:
            if value > 0 and 0 < ltv <= 55:
                market_ok = False
                status_msg = f"영업제외 (LTV {ltv:.1f}%: 타 기관 등 자력 대환 가능 수준이라 타겟 아님)"
            
            auction_date_str = str(row_dict_updated.get("매각기일", "")).strip()
            if auction_date_str:
                import re
                try:
                    clean_date = re.sub(r'[^\d\-]', '', auction_date_str.replace('.', '-').replace('/', '-'))
                    if len(clean_date) >= 8:
                        a_date = pd.to_datetime(clean_date)
                        days_left = (a_date - pd.Timestamp("today")).days
                        result.at[idx, "잔여일수"] = days_left
                        if days_left >= 30: 
                            market_ok = False
                            status_msg = f"영업제외 (매각기일 {days_left}일 남음: 당장의 절박함이 없어 시간 낭비 요소임)"
                except: pass

        result.at[idx, "심사상태"] = status_msg if not market_ok else "적격 (Approved)"

        try:
            if needs_registry_verification(row_dict_updated):
                result.at[idx, "등기부열람여부"] = "열람필수"
        except Exception: pass

        if not str(row.get("담당자메모") or "").strip():
            result.at[idx, "담당자메모"] = f"▶ 현장 영업전략: {build_owner_pitch(row_dict_updated)}"

    return result

# =========================================================================
# SECTION 1: 업로드 및 파싱
# =========================================================================
st.markdown("<div class='section-title'>📁 데이터 및 캡쳐본 스캔 분석</div>", unsafe_allow_html=True)

api_key_input = st.text_input("🔑 Google Gemini API 키 보안 입력 (한 번 입력 시 세션 유지됨)", value=st.session_state.api_key, type="password")
if api_key_input != st.session_state.api_key:
    st.session_state.api_key = api_key_input

uploaded_files = st.file_uploader(
    "스마트폰 캡쳐 여러 장, 또는 엑셀 데이터를 드래그하여 일괄 업로드", 
    type=["xlsx", "csv", "png", "jpg", "jpeg"], 
    accept_multiple_files=True, 
    label_visibility="collapsed"
)

if uploaded_files:
    image_files = []
    excel_dfs = []
    
    with st.spinner("💳 초고도 AI가 법적/재무적 데이터를 심층 파싱 중입니다 (텍스트, 감정가, 채무액 추출)..."):
        for file in uploaded_files:
            file_ext = file.name.lower()
            if file_ext.endswith((".csv", ".xlsx")):
                df = pd.read_csv(file) if file_ext.endswith(".csv") else pd.read_excel(file)
                excel_dfs.append(df)
            elif file_ext.endswith((".png", ".jpg", ".jpeg")):
                image_files.append(file)
        
        # 용량 최적화를 위해 메모리에 원본 이미지를 누적시키지 않고 분석 처리에만 사용합니다.
        # st.session_state.uploaded_images = image_files
        
        if image_files:
            if st.session_state.api_key:
                try:
                    vision_df = process_images_to_dataframe(st.session_state.api_key, image_files, DEFAULT_COLUMNS)
                    excel_dfs.append(vision_df)
                except Exception as e:
                    st.error(f"❌ 데이터 파싱 오류: {e}")
            else:
                st.warning("⚠️ API 키가 입력되지 않아 캡쳐 사진의 AI 분석이 생략되었습니다. (원본은 아래 보관함에 저장됩니다.)")
                
        if excel_dfs:
            combined_df = pd.concat(excel_dfs, ignore_index=True)
            enriched_df = enrich_dataframe(combined_df)
            st.session_state.df = enriched_df
            
            # Require 2 & 3: 적격(Approved) 자산의 캡쳐본만 저장하고, 부적격 건은 메모리에서 즉시 자동 삭제
            approved_df = enriched_df[enriched_df["심사상태"] == "적격 (Approved)"]
            approved_filenames = approved_df["원본파일명"].astype(str).tolist()
            
            # 저장할 적격 이미지 필터링
            temp_approved_images = []
            for img in image_files:
                if img.name in approved_filenames:
                    temp_approved_images.append(img)
            
            st.session_state.uploaded_images = temp_approved_images
            
            st.success("✅ 심층 평가 완료. 스크롤을 내려 결과를 확인하십시오. (부적격 건의 캡쳐본은 용량 최적화를 위해 서버에서 즉시 영구 파기되었습니다.)")

df = st.session_state.df

# =========================================================================
# SECTION 2: 심사 대시보드
# =========================================================================
st.markdown("<div class='section-title'>📈 NPL 심사 및 매칭 대시보드</div>", unsafe_allow_html=True)

if not df.empty:
    approved = df[df["심사상태"] == "적격 (Approved)"]
    rejected = df[df["심사상태"] != "적격 (Approved)"]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(f"<div class='metric-box'><div class='metric-title'>스캔된 전체 자산(건)</div><div class='metric-value'>{len(df)}</div></div>", unsafe_allow_html=True)
    col2.markdown(f"<div class='metric-box'><div class='metric-title'>타겟 영업 적격건수</div><div class='metric-value' style='color:#27ae60;'>{len(approved)}</div></div>", unsafe_allow_html=True)
    col3.markdown(f"<div class='metric-box'><div class='metric-title'>리스크 초과 및 보류</div><div class='metric-value' style='color:#c0392b;'>{len(rejected)}</div></div>", unsafe_allow_html=True)
    avg_ltv = df["추정LTV"].str.replace("%","").astype(float).mean() if not df.empty else 0
    col4.markdown(f"<div class='metric-box'><div class='metric-title'>포트폴리오 평균 LTV</div><div class='metric-value'>{avg_ltv:.1f}%</div></div>", unsafe_allow_html=True)

    if "열람필수" in df["등기부열람여부"].values:
        st.warning("⚠️ **[컴플라이언스 경고]** 해당 물건 중 가처분/가등기 등 특수 권리 하자가 존재하는 자산이 발견되었습니다. 반드시 실물 등기부등본을 교차 검증하십시오.")

    st.markdown("<h3 style='margin-top:30px; font-weight:900;'>🟢 대환/매입 타당성 적격 자산 (Target Approved)</h3>", unsafe_allow_html=True)
    if not approved.empty:
        for _, row in approved.iterrows():
            debt_fmt = f"{_safe_float(row.get('부채총액',0)):,.0f}"
            val_fmt = f"{_safe_float(row.get('감정가',0)):,.0f}"
            days_left = f"(D-{int(row.get('잔여일수', 0))})" if row.get("잔여일수") != "" else ""
            
            st.markdown(f"""
            <div class="card-passed">
                <h4><span class="badge-approved">적격</span> 사건번호: {row.get('사건번호', 'N/A')} <span style="font-size: 16px; color: #7f8c8d;">({row.get('아파트명', '주소 미상')})</span></h4>
                <div style="display:flex; justify-content:space-between; margin-top:20px; border-bottom:2px solid #f1f2f6; padding-bottom:20px;">
                    <div><div class="info-label">Scoring & Rating</div><div class="info-data">{row['분석점수']}점 ({row['분석등급']}등급)</div></div>
                    <div><div class="info-label">기일 & 추정 캡</div><div class="info-data">{row.get('매각기일','')} {days_left} | LTV {row['추정LTV']}</div></div>
                    <div><div class="info-label">부채 / 감정가</div><div class="info-data">{debt_fmt} / {val_fmt}</div></div>
                </div>
                <div style="margin-top: 20px; font-size: 16px;">
                    <b style="color:#2980b9;">🎯 펀딩/매칭 솔루션:</b> {row['추천대주']}<br>
                    <b style="color:#e67e22;">⚖️ 권리 리스크:</b> {row['권리요약']}<br>
                    <b>👤 주요 채권단:</b> {row.get('주요채권자','미상')}
                </div>
                <div class="expert-analysis-box">
                    <strong>🧠 AI 수석 심사역 종합 의견:</strong><br>{row.get('AI_심층분석','생성된 의견이 없습니다.')}
                </div>
                <p style="margin-top:15px; font-size:15px; color:#34495e; font-weight:700;">{row['담당자메모']}</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("현재 분석된 대상 중 타겟 영업 요건(적격)을 만족하는 자산이 없습니다.")
    
    # Require 2: 캡쳐 데이터 파싱이 안 되었거나 부적격인 건을 절대 삭제하지 않고 대시보드에 명시
    st.markdown("<h3 style='margin-top:50px; font-weight:900;'>🔴 수익성 미달 및 보류 자산 (Rejected or Failed)</h3>", unsafe_allow_html=True)
    if not rejected.empty:
        for _, row in rejected.iterrows():
            debt_fmt = f"{_safe_float(row.get('부채총액',0)):,.0f}"
            val_fmt = f"{_safe_float(row.get('감정가',0)):,.0f}"
            st.markdown(f"""
            <div class="card-failed">
                <h4><span class="badge-rejected">부적격/보류</span> 사건번호: {row.get('사건번호', '판독불가')}</h4>
                <p style="color: #c0392b; font-weight:900; font-size: 16px; margin: 10px 0;">차단 사유: {row['심사상태']}</p>
                <div style="display:flex; justify-content:space-between; font-size:15px; color:#2c3e50; font-weight: 500;">
                    <span>추정 LTV: <b>{row['추정LTV']}</b></span>
                    <span>총부채: {debt_fmt}</span>
                    <span>감정가: {val_fmt}</span>
                    <span>권리요약: {row['권리요약']}</span>
                </div>
                <div style="margin-top: 10px; font-size: 14px; color: #7f8c8d;">
                    AI 코멘트: {row.get('AI_심층분석','')}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("부적격 또는 판독 제한으로 보류된 자산이 없습니다.")

else:
    st.info("데이터 소스를 업로드하여 자산 평가를 시작하십시오.")

# =========================================================================
# SECTION 3: 전체 원본 및 캡쳐본 보관함 (Require 3 확인)
# =========================================================================
st.markdown("<div class='section-title'>📁 전체 데이터보관 및 캡쳐 관리</div>", unsafe_allow_html=True)
st.caption("AI 심사 결과에 따라 적격/부적격 데이터를 상하(수직)로 분리하여 모두 보관합니다. 영업에 실패했거나 불필요해진 '적격' 캡쳐본은 버튼을 눌러 수동으로 삭제할 수 있습니다.")

if not df.empty:
    approved_df = df[df["심사상태"] == "적격 (Approved)"]
    rejected_df = df[df["심사상태"] != "적격 (Approved)"]
    
    st.markdown("<h3 style='margin-top:20px; color:#27ae60;'>🟢 적격 (Approved) 텍스트 데이터</h3>", unsafe_allow_html=True)
    if not approved_df.empty:
        st.dataframe(approved_df.drop(columns=["원본파일명"], errors="ignore"), use_container_width=True)
    else:
        st.info("적격 통과된 텍스트 데이터가 없습니다.")
        
    st.markdown("<h4 style='margin-top:20px;'>📷 영업 대상 캡쳐본 증빙 서류</h4>", unsafe_allow_html=True)
    st.caption("현장 영업을 완료했거나 보관이 불필요한 원본은 [삭제] 버튼을 눌러 메모리에서 영원히 파기할 수 있습니다.")
    if st.session_state.uploaded_images:
        cols = st.columns(3)
        for i, img in enumerate(st.session_state.uploaded_images):
            with cols[i % 3]:
                st.image(img, caption=f"적격 통과: {img.name}", use_container_width=True)
                if st.button("🗑️ 캡쳐본 영구 삭제", key=f"del_img_{img.name}_{i}", use_container_width=True):
                    st.session_state.uploaded_images = [x for x in st.session_state.uploaded_images if x.name != img.name]
                    st.rerun()
    else:
        st.info("보관 중인 캡쳐본이 없거나 모두 삭제되었습니다.")

    st.markdown("<h3 style='margin-top:50px; color:#c0392b;'>🔴 부적격/보류 (Rejected) 텍스트 데이터</h3>", unsafe_allow_html=True)
    st.caption("부적격 자산의 '캡쳐본 이미지'는 데이터 최적화를 위해 AI 심사 직후 서버에서 즉시 영구 삭제되었습니다. 텍스트 판단 기록만 아래에 보관됩니다.")
    if not rejected_df.empty:
        st.dataframe(rejected_df.drop(columns=["원본파일명"], errors="ignore"), use_container_width=True)
    else:
        st.info("부적격으로 분류된 데이터가 없습니다.")
else:
    st.write("보관된 데이터가 없습니다.")

# =========================================================================
# SECTION 4: 리포트 출력
# =========================================================================
st.markdown("<div class='section-title'>🖨️ 보고서/리포트 형식 출력</div>", unsafe_allow_html=True)
if not df.empty:
    approved_df = df[df["심사상태"] == "적격 (Approved)"]
    if not approved_df.empty:
        st.caption("반드시 영업 타당성을 통과한 '적격(Approved)' 물건에 대해서만 의사결정용/영업용 리포트 파일물을 한정하여 생성합니다.")
        export_rows = approved_df.head(50).to_dict(orient="records")
        ppt_bytes = generate_pptx_bytes(export_rows)
        pdf_bytes = generate_pdf_bytes(export_rows)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 PDF 심사보고서 다운로드", data=pdf_bytes, file_name="Underwriting_Report_Approved.pdf", mime="application/pdf")
        with col2:
            st.download_button("📊 PPTX 브리핑 덱 다운로드", data=ppt_bytes, file_name="Lender_Pitch_Deck_Approved.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    else:
        st.warning("출력 가능한 '적격(Approved)' 자산 데이터가 파악되지 않았습니다.")
else:
    st.info("데이터가 없습니다.")

# =========================================================================
# SECTION 5: 영업 및 심사 플레이북 가이드
# =========================================================================
st.markdown("<div class='section-title'>📚 NPL 영업 및 협상 전략 센터 (Playbook)</div>", unsafe_allow_html=True)

with st.expander("1️⃣ [타겟팅] 유망 매입 자산 선별 기준 (Underwriting Limits)", expanded=True):
    st.markdown("""
    <div style="font-size:16px; line-height:1.6;">
    <b>[경매 취하/대환 마케팅의 절대적 요건]</b><br>
    영업 사원의 시간 낭비를 막고, 계약 성사율이 90%에 달하는 확실한 타겟만 대시보드에 <b>'🟢적격'</b>으로 올립니다.<br><br>
    
    <b>📌 영업에서 즉시 제외되는 건 (적색 경보 - 접근 금지)</b>
    <ol>
        <li><b>시간적 여유 (매각기일 30일 이상)</b>: 심리적 무장해제가 덜 되어 고금리 방어선을 치려 하지 않음.</li>
        <li><b>여유 자금 가능 (LTV 55% 이하)</b>: 시중은행으로도 자력 해결 가능하므로 대부업 유입 확률 0%.</li>
        <li><b>극단적 부실 (LTV 85% 초과)</b>: 대주단에서도 채권 회수가 불가능해 거부하는 악성 물건.</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)

with st.expander("2️⃣ [네트워킹] 파트너 대주별 승인 타겟 (Lender Criteria)", expanded=True):
    st.markdown("""
    <div style="font-size:16px; line-height:1.6;">
    시스템은 권리 및 부채비율을 계산하여 소유주에게 즉시 안내할 <b>최적의 자금 공급처</b>를 아래 기준에 따라 배정합니다.<br><br>
    
    * 🟢 <b>[초우량] A타입 (1/2금융 대환 타겟)</b> : <b>저축은행 (담당자: 김모모 팀장)</b>
      > <b>수용조건</b>: LTV 55~80% 사이. 선순위 권리 완벽. 금리 6~9%대. 가장 저렴하나 엄격.
    * 🔵 <b>[급행] B타입 (고LTV 공격적 여신)</b> : <b>우수 대부 (담당자: 박모모 이사)</b>
      > <b>수용조건</b>: LTV 80~85%. 가압류 등 일부 지저분해도 매각 가치만 나오면 2일 내 승인. 금리 12~18%. 매각 방어(시간 벌기)가 시급한 소유주에게 즉효.
    </div>
    """, unsafe_allow_html=True)
    
with st.expander("3️⃣ [협상술] 채권단 설득 및 헤어컷(탕감) 전술", expanded=True):
    st.markdown("""
    <div style="font-size:16px; line-height:1.6;">
    * 🏛️ <b>유동화/NPL 성향</b> : <code>신속한 현금회수 선호</code>. "일시불 지급할 테니 이자 및 유동화 할인율만큼 헤어컷(원금 감면) 해달라" 요구.<br>
    * 🏦 <b>1/2금융 성향</b> : <code>보수적/숫자 중시</code>. "유찰 시 배당액 손실 시뮬레이션(숫자)"을 보여주머 배당 종기 의존보다 현 대환수용이 안전함을 설득.<br>
    * 🏢 <b>공공/조세채권</b> : <code>단호함</code>. 선순위 압류는 분할납부 및 한시적 압류 해제를 통한 대환으로 우선적으로 치워야 함.
    </div>
    """, unsafe_allow_html=True)

