import streamlit as st
import boto3
import time
import json
import pandas as pd
import plotly.express as px

# ---------------------------------------------------------
# 1. 초기 설정
# ---------------------------------------------------------
st.set_page_config(page_title="100-Burst Zero-Copy Demo", layout="wide")

LAMBDA_ENDPOINT = "http://localhost:4566"
BASELINE_FUNCTION_NAME = "stress-test-baseline"
SHM_FUNCTION_NAME = "stress-test-shm"

@st.cache_resource
def get_lambda_client():
    return boto3.client("lambda", endpoint_url=LAMBDA_ENDPOINT, region_name="us-east-1",
                        aws_access_key_id="test", aws_secret_access_key="test")

lambda_client = get_lambda_client()

if "history" not in st.session_state:
    st.session_state.history = []

# ---------------------------------------------------------
# 2. 호출 함수 (내부 루프용)
# ---------------------------------------------------------
def invoke_lambda(function_name):
    try:
        start_t = time.perf_counter()
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({"test": "burst"}).encode("utf-8")
        )
        latency = (time.perf_counter() - start_t) * 1000
        return True, latency
    except:
        return False, 0

# ---------------------------------------------------------
# 3. UI 레이아웃
# ---------------------------------------------------------
st.title("🔥 100-Burst Stress Test (Single Click)")
st.markdown("단 한 번의 클릭으로 100번의 요청을 연속으로 보냅니다. **누적된 시간 차이**를 확인하세요.")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("제어판")
    
    # [핵심] 100회 연속 호출 버튼
    if st.button("🚀 100회 연타 시작 (Burst)", use_container_width=True, type="primary"):
        st.session_state.history = [] # 새 실험을 위해 초기화
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 임시 리스트에 결과 수집
        temp_history = []
        
        for i in range(1, 101):
            status_text.text(f"Running iteration {i}/100...")
            
            # Baseline 호출
            b_ok, b_lat = invoke_lambda(BASELINE_FUNCTION_NAME)
            temp_history.append({"Run": i, "Series": "Baseline", "Latency (ms)": b_lat})
            
            # SHM 호출
            s_ok, s_lat = invoke_lambda(SHM_FUNCTION_NAME)
            temp_history.append({"Run": i, "Series": "eBPF / Zero-Copy", "Latency (ms)": s_lat})
            
            progress_bar.progress(i / 100)
        
        st.session_state.history = temp_history
        status_text.success("✅ 100회 호출 완료!")

    if st.button("🗑️ 기록 초기화", use_container_width=True):
        st.session_state.history = []
        st.rerun()

with col2:
    st.subheader("📊 성능 비교 분석")
    
    if st.session_state.history:
        df = pd.DataFrame(st.session_state.history)
        
        # 1. 꺾은선 그래프 (지속성 확인)
        fig = px.line(df, x="Run", y="Latency (ms)", color="Series", markers=True,
                      color_discrete_map={"Baseline": "#EF553B", "eBPF / Zero-Copy": "#636EFA"},
                      title="100회 연속 호출 지연시간 추이")
        st.plotly_chart(fig, use_container_width=True)
        
        # 2. 누적 합계 분석 (임팩트 강조용)
        st.divider()
        summary = df.groupby("Series")["Latency (ms)"].agg(['sum', 'mean']).reset_index()
        
        c1, c2 = st.columns(2)
        baseline_total = summary[summary['Series'] == 'Baseline']['sum'].values[0]
        shm_total = summary[summary['Series'] == 'eBPF / Zero-Copy']['sum'].values[0]
        
        with c1:
            st.metric("Baseline 총 소요 시간", f"{baseline_total/1000:.2f} 초")
        with c2:
            st.metric("Zero-Copy 총 소요 시간", f"{shm_total/1000:.2f} 초", 
                      delta=f"-{(baseline_total - shm_total)/1000:.2f} 초 절감", delta_color="normal")
            
        st.write(f"👉 **결론:** Zero-Copy 사용 시, 100회 요청 기준 약 **{((baseline_total - shm_total) / baseline_total * 100):.1f}%**의 시간이 절약되었습니다.")

    else:
        st.info("왼쪽의 'Burst' 버튼을 누르면 실험이 시작됩니다.")