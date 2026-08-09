import pandas as pd
import streamlit as st
from pathlib import Path
from io import BytesIO
from report_generator import generate_pptx_bytes, generate_pdf_bytes
import time

from analysis import (
    calculate_candidate_score, classify_grade, recommend_lender, 
    build_rights_summary, suggest_candidate_flag, build_owner_pitch, 
    build_visit_advice, build_phone_pitch, build_visit_pitch,
    passes_market_filters, needs_registry_verification, _safe_float,
    get_creditor_advice
)
from vision_extractor import process_images_to_dataframe

st.set_page_config(
    page_title="NPL Underwriting Pro | 경매취하 AI 시스템", 
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
st.markdown("<div class='main-header'>🏢 NPL 매입 타당성 심사 시스템</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Underwriting Pro | 대주(Lender) 파이낸싱 및 특수 물건 매입 타당성 검증 최상위 전문가용 Risk Assessment Dashboard</div>", unsafe_allow_html=True)

# ==================== 기본 설정 ====================
DEFAULT_COLUMNS = [
    "원본파일명", "사건번호", "매각기일", "잔여일수", "법원명", "물건번호", "주소", "아파트명", "감정가", "최저매각가격", "낙찰예상가",
    "부채총액", "청산가능여부", "권리요약", "분석점수", "분석등급", "추천대주", "담당자메모",
    "KB시세", "주요채권자", "심사상태", "추정LTV", "AI_심층분석", "등기부열람여부", "근저당여부", "압류여부", "가처분여부"
]

# Session State 초기화
if "df" not in st.session_state: 
    st.session_state.df = pd.DataFrame(columns=DEFAULT_COLUMNS)
if "uploaded_images" not in st.session_state: 
    st.session_state.uploaded_images = []
if "processing_log" not in st.session_state:
    st.session_state.processing_log = []

# API Key 관리
if "api_key" not in st.session_state:
    try:
        st.session_state.api_key = st.secrets.get("GEMINI_API_KEY", "")
    except:
        st.session_state.api_key = ""

# ==================== 데이터 강화 함수 ====================
def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in DEFAULT_COLUMNS:
        if col not in result.columns: 
            result[col] = ""
            
    for idx, row in result.iterrows():
        row_dict = row.to_dict()
        score = calculate_candidate_score(row_dict)
        grade = classify_grade(score)
        
        result.at[idx, "분석점수"] = score
        result.at[idx, "분석등급"] = grade
        
        if not str(row.get("권리요약") or "").strip():
            result.at[idx, "권리요약"] = build_rights_summary(row_dict)
            
        row_dict_updated = result.loc[idx].to_dict()
        
        # LTV 계산
        debt = _safe_float(row_dict_updated.get("부채총액", 0))
        value = _safe_float(row_dict_updated.get("KB시세") or row_dict_updated.get("감정가", 0))
        ltv = (debt / value * 100) if value > 0 else 0
        result.at[idx, "추정LTV"] = f"{ltv:.1f}%"
        
        # 대주 추천
        if not str(row.get("추천대주") or "").strip():
            result.at[idx, "추천대주"] = recommend_lender(row_dict_updated)

        # 마켓 필터 적용
        try:
            market_ok = passes_market_filters(row_dict_updated)
        except Exception:
            market_ok = False

        status_msg = "부적격 (Rejected)"
        if not market_ok:
            status_msg = "❌ 부적격 (LTV 85% 한도 초과 또는 치명적 악성 권리)"
        else:
            # LTV 55% 미만 제외
            if value > 0 and 0 < ltv <= 55:
                market_ok = False
                status_msg = f"⚠️ 영업제외 (LTV {ltv:.1f}%: 타 기관 등 자력 대환 가능 수준)"
            
            # 매각기일 30일 이상 제외
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
                            status_msg = f"⏰ 영업제외 (매각기일 D-{days_left}: 절박함 없음)"
                except: 
                    pass

        result.at[idx, "심사상태"] = status_msg if not market_ok else "✅ 적격 (Approved)"

        # 등기부 열람 필요 여부
        try:
            if needs_registry_verification(row_dict_updated):
                result.at[idx, "등기부열람여부"] = "열람필수"
        except Exception: 
            pass

        # 담당자 메모
        if not str(row.get("담당자메모") or "").strip():
            result.at[idx, "담당자메모"] = f"▶ 현장 영업전략: {build_owner_pitch(row_dict_updated)}"

    return result

# =========================================================================
# SECTION 1: 업로드 및 AI 파싱
# =========================================================================
st.markdown("<div class='section-title'>📁 데이터 및 캡처본 스캔 분석</div>", unsafe_allow_html=True)

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

uploaded_files = st.file_uploader(
    "📤 스마트폰 캡처 여러 장, 또는 엑셀 데이터를 드래그하여 일괄 업로드", 
    type=["xlsx", "csv", "png", "jpg", "jpeg"], 
    accept_multiple_files=True
)

if st.button("🚀 AI 심층 분석 시작", type="primary", use_container_width=True) and uploaded_files:
    image_files = []
    excel_dfs = []
    
    st.session_state.processing_log = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    status_text.markdown("### 📊 처리 진행 상황")
    
    # 1단계: 파일 분류
    status_text.markdown("#### 1/4 파일 분류 중...")
    progress_bar.progress(25)
    time.sleep(0.5)
    
    for file in uploaded_files:
        file_ext = file.name.lower()
        if file_ext.endswith((".csv", ".xlsx")):
            st.session_state.processing_log.append(f"✓ 엑셀 파일 감지: {file.name}")
            df = pd.read_csv(file) if file_ext.endswith(".csv") else pd.read_excel(file)
            excel_dfs.append(df)
        elif file_ext.endswith((".png", ".jpg", ".jpeg")):
            st.session_state.processing_log.append(f"✓ 이미지 파일 감지: {file.name}")
            image_files.append(file)
    
    # 2단계: Vision AI 분석
    if image_files:
        status_text.markdown(f"#### 2/4 Vision AI 분석 중... ({len(image_files)}개 이미지)")
        progress_bar.progress(50)
        
        if st.session_state.api_key:
            try:
                st.session_state.processing_log.append(f"🤖 Google Gemini AI 시작...")
                vision_df = process_images_to_dataframe(st.session_state.api_key, image_files, DEFAULT_COLUMNS)
                st.session_state.processing_log.append(f"✓ AI 분석 완료: {len(vision_df)}건의 데이터 추출")
                excel_dfs.append(vision_df)
            except Exception as e:
                st.error(f"❌ AI 분석 오류: {e}")
                st.session_state.processing_log.append(f"✗ AI 오류: {str(e)}")
        else:
            st.warning("⚠️ API 키가 없어 이미지 분석을 건너뜁니다")
            st.session_state.processing_log.append("⚠️ API 키 미입력 - 이미지 분석 생략")
    
    # 3단계: 데이터 통합
    status_text.markdown("#### 3/4 데이터 통합 및 심사...")
    progress_bar.progress(75)
    time.sleep(0.3)
    
    if excel_dfs:
        combined_df = pd.concat(excel_dfs, ignore_index=True)
        st.session_state.processing_log.append(f"✓ 총 {len(combined_df)}건 데이터 통합")
        
        enriched_df = enrich_dataframe(combined_df)
        st.session_state.df = enriched_df
        st.session_state.processing_log.append("✓ 심사 로직 적용 완료")
        
        # 4단계: 이미지 필터링
        status_text.markdown("#### 4/4 적격 자산 이미지 보관...")
        progress_bar.progress(90)
        
        approved_df = enriched_df[enriched_df["심사상태"].str.contains("적격", na=False)]
        approved_filenames = approved_df["원본파일명"].astype(str).tolist()
        
        temp_approved_images = [img for img in image_files if img.name in approved_filenames]
        st.session_state.uploaded_images = temp_approved_images
        st.session_state.processing_log.append(f"✓ 적격 {len(temp_approved_images)}건 이미지 보관")
        st.session_state.processing_log.append(f"✓ 부적격 {len(image_files) - len(temp_approved_images)}건 이미지 자동 삭제")
        
        progress_bar.progress(100)
        status_text.markdown("#### ✅ 분석 완료!")
        time.sleep(0.5)
        
        st.success("🎉 심층 평가 완료! 스크롤을 내려 결과를 확인하세요")
        
        # 처리 로그 표시
        with st.expander("📋 상세 처리 로그 보기"):
            for log in st.session_state.processing_log:
                st.text(log)

df = st.session_state.df

# =========================================================================
# SECTION 2: 대시보드
# =========================================================================
st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📈 NPL 심사 및 매칭 대시보드</div>", unsafe_allow_html=True)

if not df.empty:
    approved = df[df["심사상태"].str.contains("적격", na=False)]
    rejected = df[~df["심사상태"].str.contains("적격", na=False)]
    
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
            <div style='font-size:14px; color:#94a3b8; margin-top:10px;'>타겟 영업 적격</div>
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
        avg_ltv = df["추정LTV"].str.replace("%","").astype(float).mean() if not df.empty else 0
        ltv_color = "#22c55e" if avg_ltv < 75 else "#f59e0b" if avg_ltv < 85 else "#ef4444"
        st.markdown(f"""
        <div class='metric-box'>
            <div class='metric-title'>📊 Average LTV</div>
            <div class='metric-value' style='background:linear-gradient(135deg, {ltv_color} 0%, {ltv_color} 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent;'>{avg_ltv:.1f}%</div>
            <div style='font-size:14px; color:#94a3b8; margin-top:10px;'>포트폴리오 평균</div>
        </div>
        """, unsafe_allow_html=True)
    
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
    st.markdown("<h2 style='color:#22c55e; font-weight:900; margin:40px 0 30px 0;'>🟢 대환/매입 타당성 적격 자산 (Target Approved)</h2>", unsafe_allow_html=True)
    
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
                        <strong style='color:#3b82f6;'>🎯 펀딩/매칭 솔루션:</strong><br>
                        <span style='font-size:16px;'>{row['추천대주']}</span>
                    </p>
                    <p style='font-size:18px; margin:10px 0;'>
                        <strong style='color:#f59e0b;'>⚖️ 권리 리스크:</strong><br>
                        <span style='font-size:16px;'>{row['권리요약']}</span>
                    </p>
                    <p style='font-size:18px; margin:10px 0;'>
                        <strong style='color:#8b5cf6;'>👤 주요 채권단:</strong><br>
                        <span style='font-size:16px;'>{creditor_name}</span>
                    </p>
                    {"<p style='font-size:15px; margin:15px 0 0 0; padding:15px; background:#fef3c7; border-radius:8px; color:#78350f;'><strong>💡 채권자 대응 전략:</strong><br>" + creditor_advice + "</p>" if creditor_advice else ""}
                </div>
                
                <div class="expert-analysis-box">
                    <strong style='font-size:18px;'>🧠 AI 수석 심사역 종합 의견:</strong><br>
                    <p style='margin-top:15px; line-height:1.8;'>{row.get('AI_심층분석','생성된 의견이 없습니다.')}</p>
                </div>
                
                <div style='margin-top:25px; padding:20px; background:#eff6ff; border-radius:12px;'>
                    <strong style='color:#1e40af; font-size:16px;'>📞 현장 영업 가이드:</strong><br>
                    <p style='margin-top:10px; font-size:15px; color:#1e293b;'>{row['담당자메모']}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("📭 현재 분석된 대상 중 타겟 영업 요건(적격)을 만족하는 자산이 없습니다.")
    
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
    approved_df = df[df["심사상태"].str.contains("적격", na=False)]
    rejected_df = df[~df["심사상태"].str.contains("적격", na=False)]
    
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
        
        st.markdown("### 📷 영업 대상 캡처본 증빙 서류")
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
st.markdown("<div class='section-title'>📄 보고서/리포트 형식 출력</div>", unsafe_allow_html=True)

if not df.empty:
    approved_df = df[df["심사상태"].str.contains("적격", na=False)]
    if not approved_df.empty:
        st.markdown("#### 💼 의사결정용 전문 리포트 생성")
        st.caption("반드시 영업 타당성을 통과한 '적격(Approved)' 물건에 대해서만 리포트를 생성합니다.")
        
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
                file_name="Lender_Pitch_Deck_Approved.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True
            )
    else:
        st.warning("출력 가능한 '적격(Approved)' 자산 데이터가 없습니다.")
else:
    st.info("데이터가 없습니다.")

# =========================================================================
# SECTION 5: 영업 플레이북 - 대부업체 상세 정보
# =========================================================================
st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📚 NPL 영업 및 협상 전략 센터 (Playbook)</div>", unsafe_allow_html=True)

with st.expander("1️⃣ [타겟팅] 유망 매입 자산 선별 기준 (Underwriting Limits)", expanded=False):
    st.markdown("""
    <div style="font-size:16px; line-height:1.8; padding:20px;">
    <h3 style='color:#1e293b; font-weight:900;'>경매 취하/대환 마케팅의 절대적 요건</h3>
    <p>영업 사원의 시간 낭비를 막고, 계약 성사율이 90%에 달하는 확실한 타겟만 대시보드에 <span style='background:#dcfce7; padding:2px 8px; border-radius:4px; font-weight:700;'>적격</span>으로 올립니다.</p>
    
    <h4 style='color:#ef4444; font-weight:900; margin-top:30px;'>📌 영업에서 즉시 제외되는 건 (적색 경보)</h4>
    <ol style='line-height:2;'>
        <li><strong>시간적 여유 (매각기일 30일 이상)</strong><br>심리적 무장해제가 덜 되어 고금리 방어선을 치려 함. 절박함이 없어 접근 금지.</li>
        <li><strong>여유 자금 가능 (LTV 55% 이하)</strong><br>시중은행으로도 자력 해결 가능하므로 대부업 유입 확률 0%. 시간 낭비.</li>
        <li><strong>극단적 부실 (LTV 85% 초과)</strong><br>대주단에서도 채권 회수가 불가능해 거부하는 악성 물건. 우리도 손대지 않음.</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)

with st.expander("2️⃣ [네트워킹] 파트너 대주별 승인 기준 및 실제 연락처", expanded=False):
    st.markdown("""
    <div style='padding:20px;'>
        <h3 style='color:#1e293b; font-weight:900; margin-bottom:25px;'>🤝 협력 대주 네트워크 (실제 연락처)</h3>
        <p style='font-size:16px; margin-bottom:30px;'>시스템이 LTV와 권리 상황을 분석하여 최적의 대주를 자동 매칭합니다.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # A타입 - 저축은행
    st.markdown("""
    <div class='lender-card' style='border-left-color:#22c55e;'>
        <div class='lender-name'>🟢 A타입: 저축은행 (1/2금융 대환 타겟)</div>
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
        <div class='lender-name'>🔵 B타입: 우수 대부업체 (고LTV 공격적 여신)</div>
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
        <div class='lender-name'>🔴 C타입: NPL 전문 대주 (특수물건 · 고위험)</div>
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
    <p style='font-weight:700; font-size:16px; margin-bottom:10px;'>© 2026 NPL Underwriting Pro</p>
    <p>Powered by Google Gemini AI | Built with Streamlit</p>
    <p style='margin-top:20px; font-size:13px;'>이 시스템은 전문가용 의사결정 보조 도구입니다. 최종 판단은 반드시 실물 등기부와 현장 실사를 통해 검증하십시오.</p>
</div>
""", unsafe_allow_html=True)
