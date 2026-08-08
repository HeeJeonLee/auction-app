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

# [최상위 전문가용] 디스플레이 포맷 설정
st.set_page_config(page_title="PropTech Underwriting System", page_icon="🏢", layout="wide", initial_sidebar_state="collapsed")

# 금융/전문가 포털 수준의 Custom CSS
st.markdown("""
<style>
    /* Global Typography & Palette */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
        background-color: #f0f2f6;
    }
    
    /* Executive KPI Dashboard styling */
    .metric-box {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        border-top: 4px solid #1f3a93;
        text-align: left;
        margin-bottom: 20px;
    }
    .metric-value { font-size: 28px; font-weight: 700; color: #1f3a93; margin: 5px 0; }
    .metric-title { font-size: 14px; font-weight: 500; color: #666; }
    
    /* Passed/Failed Cards */
    .card-passed { 
        background: linear-gradient(135deg, #ffffff 0%, #f9fbfd 100%);
        padding: 25px; 
        border-radius: 12px; 
        margin-bottom: 20px; 
        border: 1px solid #e1e8ed;
        border-left: 6px solid #2ecc71;
        box-shadow: 0 4px 15px rgba(0,0,0,0.03); 
    }
    .card-failed { 
        background: linear-gradient(135deg, #ffffff 0%, #fdf8f8 100%);
        padding: 25px; 
        border-radius: 12px; 
        margin-bottom: 20px; 
        border: 1px solid #e1e8ed;
        border-left: 6px solid #e74c3c;
        box-shadow: 0 4px 15px rgba(0,0,0,0.03); 
    }
    
    .expert-analysis-box {
        background-color: #f8f9fa;
        border-left: 4px solid #f39c12;
        padding: 15px;
        margin-top: 15px;
        font-size: 0.95em;
        line-height: 1.6;
        color: #333;
    }

    .badge-approved { background: #e8f8f5; color: #2ecc71; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
    .badge-rejected { background: #fdedec; color: #e74c3c; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
    
    .stDownloadButton>button { width: 100%; border-radius: 6px; font-weight: bold; background-color: #1f3a93; color: white; border: none; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#1f3a93; font-weight:800;'>🏦 심층 권리·수익성 분석 시스템 (Underwriting Pro v2.0)</h2>", unsafe_allow_html=True)
st.caption("대주(Lender) 파이낸싱 및 NPL 매입 타당성 검토를 위한 전문가용 Risk Assessment Dashboard")

DEFAULT_COLUMNS = [
    "사건번호", "매각기일", "잔여일수", "법원명", "물건번호", "주소", "아파트명", "감정가", "최저매각가격", "낙찰예상가",
    "부채총액", "청산가능여부", "권리요약", "분석점수", "분석등급", "추천대주", "담당자메모",
    "KB시세", "주요채권자", "심사상태", "추정LTV", "AI_심층분석", "등기부열람여부", "근저당여부", "압류여부", "가처분여부"
]

if "df" not in st.session_state: st.session_state.df = pd.DataFrame(columns=DEFAULT_COLUMNS)
if "uploaded_images" not in st.session_state: st.session_state.uploaded_images = []

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
        
        # Financial Math (LTV Calculation)
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
            status_msg = "부적격 (LTV 85% 한도 초과 또는 악성 권리)"
        else:
            # 1. 영업 효율성 필터 1: LTV 55% 이하 (자력 상환 가능)
            if value > 0 and 0 < ltv <= 55:
                market_ok = False
                status_msg = f"영업제외 (LTV {ltv:.1f}%: 1/2금융권 등 자력 대환 가능 수준이라 타겟 아님)"
            
            # 2. 영업 효율성 필터 2: 매각기일 여유 (절박함 부족)
            auction_date_str = str(row_dict_updated.get("매각기일", "")).strip()
            if auction_date_str:
                import re
                try:
                    clean_date = re.sub(r'[^\d\-]', '', auction_date_str.replace('.', '-').replace('/', '-'))
                    if len(clean_date) >= 8:
                        a_date = pd.to_datetime(clean_date)
                        days_left = (a_date - pd.Timestamp("today")).days
                        result.at[idx, "잔여일수"] = days_left
                        if days_left >= 30: # 기일이 30일 이상 크게 남았을 때
                            market_ok = False
                            status_msg = f"영업제외 (매각기일 {days_left}일 남음: 아직 시간적 여유가 있어 영업 효율성 낮음)"
                        elif days_left < 0:
                            market_ok = False
                            status_msg = f"영업제외 (이미 매각기일이 지났거나 임박함)"
                except:
                    pass

        if not market_ok:
            result.at[idx, "심사상태"] = status_msg
        else:
            result.at[idx, "심사상태"] = "적격 (Approved)"

        try:
            if needs_registry_verification(row_dict_updated):
                result.at[idx, "등기부열람여부"] = "열람필수"
        except Exception: pass

        if not str(row.get("담당자메모") or "").strip():
            result.at[idx, "담당자메모"] = f"▶ 영업전략: {build_owner_pitch(row_dict_updated)}"

    return result

st.markdown("---")
st.markdown("#### 1. 대상 물건 데이터 수집 (Document Ingestion)")

api_key_default = ""
try: api_key_default = st.secrets.get("GEMINI_API_KEY", "")
except: pass

api_key = st.text_input("🔑 금융 데이터 파싱용 API Key", value=api_key_default, type="password")

uploaded_files = st.file_uploader(
    "경매 정보지(캡쳐) 또는 데이터 엑셀 스캔", 
    type=["xlsx", "csv", "png", "jpg", "jpeg"], 
    accept_multiple_files=True, 
    label_visibility="collapsed"
)

if uploaded_files:
    image_files = []
    excel_dfs = []
    
    with st.spinner("💳 법적/재무적 데이터를 추출 및 분석 중입니다. 잠시만 기다려주십시오..."):
        for file in uploaded_files:
            file_ext = file.name.lower()
            if file_ext.endswith((".csv", ".xlsx")):
                df = pd.read_csv(file) if file_ext.endswith(".csv") else pd.read_excel(file)
                excel_dfs.append(df)
            elif file_ext.endswith((".png", ".jpg", ".jpeg")):
                image_files.append(file)
        
        st.session_state.uploaded_images = image_files
        
        if image_files and api_key:
            try:
                vision_df = process_images_to_dataframe(api_key, image_files, DEFAULT_COLUMNS)
                excel_dfs.append(vision_df)
            except Exception as e:
                st.error(f"❌ 데이터 파싱 오류: {e}")
                
        if excel_dfs:
            combined_df = pd.concat(excel_dfs, ignore_index=True)
            st.session_state.df = enrich_dataframe(combined_df)
            st.success("✅ 심사 완료. 하단의 대시보드(Dashboard)를 통해 확인하십시오.")

st.markdown("---")
df = st.session_state.df

tab1, tab2, tab3, tab4 = st.tabs(["📈 NPL 심사 대시보드", "📚 영업·심사 플레이북(가이드)", "📁 캡쳐본 및 전체 데이터", "🖨️ 보고서 출력"])

with tab1:
    if not df.empty:
        approved = df[df["심사상태"] == "적격 (Approved)"]
        rejected = df[df["심사상태"] == "부적격 (Rejected)"]
        
        # Top KPI Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.markdown(f"<div class='metric-box'><div class='metric-title'>분석된 총 자산(건)</div><div class='metric-value'>{len(df)}</div></div>", unsafe_allow_html=True)
        col2.markdown(f"<div class='metric-box'><div class='metric-title'>파이낸싱 적격건수</div><div class='metric-value' style='color:#2ecc71;'>{len(approved)}</div></div>", unsafe_allow_html=True)
        col3.markdown(f"<div class='metric-box'><div class='metric-title'>리스크 초과(부적격)</div><div class='metric-value' style='color:#e74c3c;'>{len(rejected)}</div></div>", unsafe_allow_html=True)
        avg_ltv = df["추정LTV"].str.replace("%","").astype(float).mean() if not df.empty else 0
        col4.markdown(f"<div class='metric-box'><div class='metric-title'>포트폴리오 평균 LTV</div><div class='metric-value'>{avg_ltv:.1f}%</div></div>", unsafe_allow_html=True)

        # 등기부등본 열람 필요 여부 경고
        if "열람필수" in df["등기부열람여부"].values:
            st.warning("⚠️ **[컴플라이언스 경고]** 해당 물건 중 가처분/가등기 등 특수 권리 하자가 존재하는 자산이 발견되었습니다. 반드시 실물 등기부등본을 교차 검증하십시오.")

        st.markdown("<h3 style='margin-top:30px; font-weight:700;'>🟢 대환/매입 타당성 적격 자산 (Approved Assets)</h3>", unsafe_allow_html=True)
        for _, row in approved.iterrows():
            debt_fmt = f"{_safe_float(row.get('부채총액',0)):,.0f}"
            val_fmt = f"{_safe_float(row.get('감정가',0)):,.0f}"
            st.markdown(f"""
            <div class="card-passed">
                <h4><span class="badge-approved">적격</span> 사건번호: {row.get('사건번호', 'N/A')} <span style="font-size: 16px; color: #555;">({row.get('아파트명', '주소지 미상')})</span></h4>
                <div style="display:flex; justify-content:space-between; margin-top:15px; border-bottom:1px solid #eee; padding-bottom:15px;">
                    <div><b>Scoring & Rating:</b> {row['분석점수']}점 ({row['분석등급']}등급)</div>
                    <div><b>추정 LTV:</b> {row['추정LTV']}</div>
                    <div><b>부채 / 감정가:</b> {debt_fmt} / {val_fmt}</div>
                </div>
                <div style="margin-top: 15px;">
                    <b style="color:#1f3a93;">🎯 펀딩/매칭 솔루션:</b> {row['추천대주']}<br>
                    <b style="color:#e67e22;">⚖️ 권리 리스크:</b> {row['권리요약']}<br>
                    <b>👤 주요 채권단:</b> {row.get('주요채권자','미상')}
                </div>
                <div class="expert-analysis-box">
                    <strong>🧠 AI 선임 심사역 코멘트:</strong><br>{row.get('AI_심층분석','상세 의견이 생성되지 않았습니다.')}
                </div>
                <p style="margin-top:10px; font-size:13px; color:#555;">{row['담당자메모']}</p>
            </div>
            """, unsafe_allow_html=True)
        
        if not rejected.empty:
            st.markdown("<h3 style='margin-top:40px; font-weight:700;'>🔴 수익성 미달 및 영업 비효율 자산 (Rejected Assets)</h3>", unsafe_allow_html=True)
            for _, row in rejected.iterrows():
                debt_fmt = f"{_safe_float(row.get('부채총액',0)):,.0f}"
                val_fmt = f"{_safe_float(row.get('감정가',0)):,.0f}"
                date_fmt = row.get("매각기일", "미상")
                days_left = row.get("잔여일수", "")
                days_str = f"(D-{int(days_left)})" if days_left != "" else ""
                
                st.markdown(f"""
                <div class="card-failed">
                    <h4><span class="badge-rejected">영업 제외</span> 사건번호: {row.get('사건번호', 'N/A')}</h4>
                    <p style="color: #e74c3c; font-weight:bold;">사유: {row['심사상태']}</p>
                    <div style="display:flex; justify-content:space-between; font-size:14px; color:#555;">
                        <span>추정 LTV: <b>{row['추정LTV']}</b></span>
                        <span>매각기일: <b>{date_fmt} {days_str}</b></span>
                        <span>총부채: {debt_fmt}</span>
                        <span>감정가: {val_fmt}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("데이터 소스를 업로드하여 자산 평가를 시작하십시오.")

with tab2:
    st.markdown("#### � 투자 심사 및 영업 (Playbook) 매뉴얼")
    st.markdown("본 시스템의 알고리즘 판단 기준 및 파트너 대주/채권자별 협상 가이드라인입니다. 소유주 설득 시 본 자료를 논리적 근거로 활용하십시오.")
    
    with st.expander("1️⃣ [소유주 설득 논리] 유망 경매건 선별 기준 (Underwriting Criteria)", expanded=True):
        st.markdown("""
        **[왜 소유주가 경매 취하/대환을 선택해야 하는가?]**
        우리의 1차 타겟 물건은 "경매 매각 시 소유주에게 빚이 남거나 현금을 잃지만, 당장의 즉각적인 대환 자금이 수혈되면 살릴 수 있는 엄청난 절박함이 있는 자산"입니다.
        
        **📌 [타겟 제외 기준 (시간 낭비 방지)]**
        시간을 낭비하지 않기 위해 아래의 조건에 해당하는 물건은 시스템이 🔴**부적격(영업제외)** 으로 쳐냅니다.
        1. **시간적 여유 (매각기일 30일 이상 남음)**: 당장의 탈락 위기가 아니면 고금리 대부를 쓰려 하지 않음.
        2. **너무 낮은 부채 여력 (LTV 55% 이하)**: 본인이 평범한 1/2금융권 대출로 충분히 해결할 수 있어 우리의 타겟이 아님.
        3. **너무 높은 부채 악성 (LTV 85% 이상)**: 대부업체도 회수하기 위험해 대출을 거부함.
        
        * **A타입 적격 (우량 자산)**: LTV 55~80% 사이. 권리가 깨끗하고 매각기일이 한 달 내외로 임박한 자산. 
          👉 *[설득 포인트]* "사장님, 다음 달이 기일입니다. 이대로면 수천만 원 손해입니다. 즉시 취하하고 저축은행 일반 대출로 갈아타서 신용도 지키고 이자도 방어하십시오."
        * **B타입 적격 (기회 자산)**: LTV 80~85%. 타 기관 대출이 막혔으나 매각 방어가 시급한 기일 임박 자산.
          👉 *[설득 포인트]* "현재 타사 대출은 모두 불가능한 상황입니다. 하지만 저희 특화 대주를 통하면 강제 매각을 즉시 멈출 자금을 오늘 쏠 수 있습니다."
        """)

    with st.expander("2️⃣ [네트워크] 파트너 대부업체 프로필 및 수용 조건 (Lender Matching)", expanded=False):
        st.markdown("""
        **[대주별 리스크 테이킹 성향 및 매칭 기준]**
        시스템은 아래의 각 대주 성향을 수학적으로 계산하여 최적의 대주를 화면에 출력합니다.
        
        * 🟢 **A타입 (1/2금융권 대환 타겟)** : `🟢🟢저축은행 / 담당자: 김모모 팀장 (02-XXX-XXXX)`
          > **[수용조건]** LTV 80~82% 이하, 선순위 근저당 외 깨끗한 권리. 
          > **[금리/특성]** 6~9%대. 가장 저렴하나 심사가 매우 까다로움.
        * 🔵 **B타입 (고LTV 공격적 대주)** : `🔵🔵대부 / 담당자: 박모모 이사 (02-YYY-YYYY)`
          > **[수용조건]** LTV 90% 수준까지 허용. 후순위 가압류 1~2개 존재해도 매각 여력 있으면 승인.
          > **[금리/특성]** 12~18%대. 금리는 높으나 속도가 매우 빠르고 승인율이 높음. 당장의 경매 취하 자금이 급한 소유주에게 필수적.
        * 🔴 **C타입 (NPL·특수물건 전문 대주)** : `🔴🔴NPL자산관리 / 담당자: 최모모 대표 (02-ZZZ-ZZZZ)`
          > **[수용조건]** 한도 초과, NPL 론세일 방식, 지분 경매 등 법적 분쟁 예상 건.
          > **[금리/특성]** 대환보다는 채권 매입(할인 매입) 위주로 접근.
        """)
        
    with st.expander("3️⃣ [실무자 핸드북] 채권자별 협상 가이드 및 헤어컷 전략", expanded=False):
        st.markdown("""
        **[어떻게 빚을 줄여주고 소유주를 구출할 것인가?]**
        
        * 🏛️ **유동화/NPL 성향 (F&I, 자산관리)** : `신속한 현금회수 선호`. 경매 배당기일까지 기다리는 것을 싫어하므로, "당장 일시불로 갚을테니 이자 면제 및 원금 헤어컷(할인) 해달라"는 제안이 매우 잘 통함.
        * 🏦 **1금융 성향 (농협, 수협, 시중은행)** : `내부 규정 엄격`. 원금 감면은 불가능. "전액 상환할 테니 지연배상금(연체이자)만 일부 면제해 달라"고 현실적으로 타진해야 함.
        * 💳 **2/3금융 성향 (캐피탈, 저축은행, 대부)** : `숫자가 생명`. "경매로 가서 유찰되면 당신들 채권 배당 못 받는다. 차라리 지금 우리가 대환해줄 때 원금이라도 확실히 건져라"라며 배당표 손실 시뮬레이션을 제시하여 취하 유도.
        * 🏢 **공공/조세채권 (건강보험, 세무서)** : `단호함`. 법정기일이 빠르면 우리 대주가 선순위를 뺏기므로 무조건 100% 현금 완납하거나, 분할납부 조건으로 압류 한시적 해제를 읍소해야 함.
        """)

with tab3:
    st.markdown("#### �📁 Raw Data & 증빙 스캔본")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        
        if st.session_state.uploaded_images:
            st.markdown("---")
            st.markdown("#### 📷 물건 증빙(스캔) 보관함")
            cols = st.columns(3)
            for i, img in enumerate(st.session_state.uploaded_images):
                cols[i%3].image(img, caption=img.name, use_container_width=True)
    else:
        st.write("표시할 Raw Data가 없습니다.")

with tab3:
    st.markdown("#### 🖨️ 투자자/내부 위원회용 심사보고서 출력")
    if not df.empty and len(df[df["심사상태"] == "적격 (Approved)"]) > 0:
        approved_df = df[df["심사상태"] == "적격 (Approved)"]
        export_rows = approved_df.head(10).to_dict(orient="records")
        ppt_bytes = generate_pptx_bytes(export_rows)
        pdf_bytes = generate_pdf_bytes(export_rows)

        st.caption("권리 이력이 안전하고 수익 구조가 확보된 '적격' 자산에 한하여 위원회 보고용 PDF 및 브리핑용 PPTX가 생성됩니다.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 PDF 심사보고서 다운로드", data=pdf_bytes, file_name="Underwriting_Report.pdf", mime="application/pdf")
        with col2:
            st.download_button("📊 PPTX 대주 브리핑 덱 다운로드", data=ppt_bytes, file_name="Lender_Pitch_Deck.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    else:
        st.warning("출력 가능한 '적격' 자산 데이터가 존재하지 않습니다.")

