import streamlit as st
import boto3
import time
import json
import pandas as pd
import plotly.express as px
from botocore.exceptions import ClientError, BotoCoreError

# ---------------------------------------------------------
# 0. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="Zero-Copy Lambda Demo", layout="wide")

# ---------------------------------------------------------
# 1. MiniStack 연결 설정
# ---------------------------------------------------------
LAMBDA_ENDPOINT = "http://localhost:4566"

BASELINE_FUNCTION_NAME = "stress-test-baseline"
SHM_FUNCTION_NAME = "stress-test-shm"

AWS_REGION = "us-east-1"

@st.cache_resource
def get_lambda_client():
    return boto3.client(
        "lambda",
        endpoint_url=LAMBDA_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

lambda_client = get_lambda_client()

# 세션 상태 초기화
if "history" not in st.session_state:
    st.session_state.history = []

if "run_count" not in st.session_state:
    st.session_state.run_count = 0

# ---------------------------------------------------------
# 2. 유틸 함수
# ---------------------------------------------------------
def safe_json_loads(text):
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def parse_lambda_payload(payload_stream):
    raw_bytes = payload_stream.read()
    raw_text = raw_bytes.decode("utf-8", errors="replace").strip() if raw_bytes else ""

    if not raw_text:
        return {}

    parsed = safe_json_loads(raw_text)

    if parsed is None:
        return {"raw_response": raw_text}

    if isinstance(parsed, dict) and "body" in parsed:
        body = parsed.get("body")
        if isinstance(body, str):
            parsed_body = safe_json_loads(body)
            if parsed_body is not None:
                return parsed_body
            return {"body": body}
        return body if body is not None else {}

    return parsed

def check_function_exists(function_name):
    try:
        lambda_client.get_function(FunctionName=function_name)
        return True, None
    except ClientError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def invoke_single_lambda(function_name, series_name, invoke_type):
    payload = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "demo-web-bucket"},
                    "object": {"key": "dummy_50mb.txt"}
                }
            }
        ]
    }

    exists, err = check_function_exists(function_name)
    if not exists:
        return {
            "success": False, "series": series_name, "function_name": function_name,
            "error": f"함수 '{function_name}'를 찾을 수 없습니다.", "latency_ms": 0, "result": {}
        }

    start_time = time.perf_counter()

    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8")
        )

        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000

        function_error = response.get("FunctionError")
        parsed_result = parse_lambda_payload(response["Payload"])

        if function_error:
            return {
                "success": False, "series": series_name, "function_name": function_name,
                "error": f"Lambda 오류: {function_error}", "latency_ms": latency_ms, "result": parsed_result
            }

        return {
            "success": True, "series": series_name, "function_name": function_name,
            "error": None, "latency_ms": latency_ms, "result": parsed_result
        }

    except Exception as e:
        return {
            "success": False, "series": series_name, "function_name": function_name,
            "error": f"오류 발생: {e}", "latency_ms": 0, "result": {}
        }

def invoke_both_lambdas():
    invoke_type = "Cold Start" if st.session_state.run_count == 0 else "Warm Start"
    run_id = st.session_state.run_count + 1
    now_str = time.strftime("%H:%M:%S")

    baseline_result = invoke_single_lambda(BASELINE_FUNCTION_NAME, "Baseline", invoke_type)
    shm_result = invoke_single_lambda(SHM_FUNCTION_NAME, "eBPF / Zero-Copy", invoke_type)

    for result in [baseline_result, shm_result]:
        zero_copy_data = "N/A"
        if isinstance(result["result"], dict):
            zero_copy_data = result["result"].get("zero_copy_config", "N/A")

        st.session_state.history.append({
            "Run": run_id,
            "Timestamp": now_str,
            "Invoke Type": invoke_type,
            "Series": result["series"],
            "Latency (ms)": result["latency_ms"],
            "Zero-Copy Data": zero_copy_data,
            "Success": result["success"],
            "Function Name": result["function_name"],
            "Error": result["error"] if result["error"] else ""
        })

    st.session_state.run_count = run_id
    return baseline_result, shm_result

# ---------------------------------------------------------
# 3. 실시간 대시보드 렌더링 함수
# ---------------------------------------------------------
def draw_dashboard(chart_container, table_container):
    if len(st.session_state.history) > 0:
        df = pd.DataFrame(st.session_state.history)
        graph_df = df[df["Success"] == True].copy()

        with chart_container.container():
            if len(graph_df) > 0:
                fig = px.line(
                    graph_df, x="Run", y="Latency (ms)", color="Series", markers=True,
                    title="실시간 지연 시간 추이 (Cold vs Warm Start 비교)",
                    color_discrete_map={"Baseline": "red", "eBPF / Zero-Copy": "blue"}
                )
                fig.update_layout(xaxis_title="호출 횟수 (Run)", yaxis_title="지연 시간 (ms)")
                st.plotly_chart(fig, use_container_width=True)

        with table_container.container():
            st.markdown("### 실시간 호출 기록")
            st.dataframe(df[["Run", "Invoke Type", "Series", "Latency (ms)"]].tail(10), use_container_width=True)

# ---------------------------------------------------------
# 4. 웹 페이지 UI
# ---------------------------------------------------------
st.title("🚀 Zero-Copy Serverless 최적화 실시간 데모")
st.markdown("이 대시보드는 **Baseline 방식**과 **eBPF / Shared Memory 방식**을 동시에 호출하여 호출 지연 시간을 비교 시각화합니다.")

col1, col2 = st.columns([1, 2])

# UI 구역(Placeholder) 미리 할당
with col2:
    chart_placeholder = st.empty()
    table_placeholder = st.empty()

with col1:
    st.subheader("제어 패널")
    
    # 단일 호출 버튼
    if st.button("🔥 단일 호출 (1회)", use_container_width=True):
        with st.spinner("호출 중..."):
            invoke_both_lambdas()
            draw_dashboard(chart_placeholder, table_placeholder)

    # 연속 100회 호출 버튼 (핵심 추가 기능)
    if st.button("🚀 100회 자동 테스트 (1초 간격)", use_container_width=True):
        st.session_state.history = []
        st.session_state.run_count = 0
        
        status_text = st.empty()
        progress_bar = st.progress(0)

        for i in range(100):
            status_text.info(f"테스트 진행 중... ({i+1}/100)")
            invoke_both_lambdas()
            
            # 차트와 테이블을 실시간으로 덮어씌워 애니메이션 효과 부여
            draw_dashboard(chart_placeholder, table_placeholder)
            
            progress_bar.progress((i + 1) / 100)
            time.sleep(1) # 1초 대기 후 다음 호출
            
        status_text.success("✅ 100회 스트레스 테스트가 완료되었습니다!")

    if st.button("🗑️ 기록 초기화", use_container_width=True):
        st.session_state.history = []
        st.session_state.run_count = 0
        st.rerun()

# 페이지 첫 로드 시 기존 데이터가 있으면 그려줌
if len(st.session_state.history) > 0:
    draw_dashboard(chart_placeholder, table_placeholder)
