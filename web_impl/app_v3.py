import streamlit as st
import boto3
import time
import json
import pandas as pd
import plotly.express as px
from botocore.exceptions import ClientError, BotoCoreError

# ---------------------------------------------------------
# 0. Page config
# ---------------------------------------------------------
st.set_page_config(page_title="Zero-Copy Lambda Demo", layout="wide")

# ---------------------------------------------------------
# 1. MiniStack connection settings
# ---------------------------------------------------------
LAMBDA_ENDPOINT = "http://localhost:4566"

BASELINE_FUNCTION_NAME = "stress-test-baseline"
SHM_FUNCTION_NAME = "stress-test-shm"

AWS_REGION = "us-east-1"
INTERNAL_CLICK_COUNT = 500

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

# ---------------------------------------------------------
# 2. Session state init
# ---------------------------------------------------------
if "history" not in st.session_state:
    st.session_state.history = []

if "run_count" not in st.session_state:
    st.session_state.run_count = 0

if "chart_render_count" not in st.session_state:
    st.session_state.chart_render_count = 0

if "table_render_count" not in st.session_state:
    st.session_state.table_render_count = 0

if "last_baseline_result" not in st.session_state:
    st.session_state.last_baseline_result = None

if "last_shm_result" not in st.session_state:
    st.session_state.last_shm_result = None

if "last_latency_diff" not in st.session_state:
    st.session_state.last_latency_diff = None

# ---------------------------------------------------------
# 3. Utility functions
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
            "success": False,
            "series": series_name,
            "function_name": function_name,
            "error": f"함수 '{function_name}'를 찾을 수 없습니다. {err}",
            "latency_ms": 0,
            "result": {}
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
                "success": False,
                "series": series_name,
                "function_name": function_name,
                "error": f"Lambda 오류: {function_error}",
                "latency_ms": latency_ms,
                "result": parsed_result
            }

        return {
            "success": True,
            "series": series_name,
            "function_name": function_name,
            "error": None,
            "latency_ms": latency_ms,
            "result": parsed_result
        }

    except (ClientError, BotoCoreError) as e:
        return {
            "success": False,
            "series": series_name,
            "function_name": function_name,
            "error": f"AWS/Boto3 오류: {e}",
            "latency_ms": 0,
            "result": {}
        }
    except Exception as e:
        return {
            "success": False,
            "series": series_name,
            "function_name": function_name,
            "error": f"오류 발생: {e}",
            "latency_ms": 0,
            "result": {}
        }

def append_result_to_history(result, run_id, invoke_type, timestamp_str):
    zero_copy_data = "N/A"
    if isinstance(result["result"], dict):
        zero_copy_data = result["result"].get("zero_copy_config", "N/A")

    st.session_state.history.append({
        "Run": run_id,
        "Timestamp": timestamp_str,
        "Invoke Type": invoke_type,
        "Series": result["series"],
        "Latency (ms)": result["latency_ms"],
        "Zero-Copy Data": zero_copy_data,
        "Success": result["success"],
        "Function Name": result["function_name"],
        "Error": result["error"] if result["error"] else ""
    })

def store_last_results(baseline_result, shm_result):
    st.session_state.last_baseline_result = baseline_result
    st.session_state.last_shm_result = shm_result

    if baseline_result and shm_result:
        if baseline_result["success"] and shm_result["success"]:
            st.session_state.last_latency_diff = (
                baseline_result["latency_ms"] - shm_result["latency_ms"]
            )
        else:
            st.session_state.last_latency_diff = None

def invoke_both_lambdas_once(store_history=True):
    invoke_type = "Cold Start" if st.session_state.run_count == 0 else "Warm Start"
    run_id = st.session_state.run_count + 1
    now_str = time.strftime("%H:%M:%S")

    baseline_result = invoke_single_lambda(BASELINE_FUNCTION_NAME, "Baseline", invoke_type)
    shm_result = invoke_single_lambda(SHM_FUNCTION_NAME, "eBPF / Zero-Copy", invoke_type)

    if store_history:
        append_result_to_history(baseline_result, run_id, invoke_type, now_str)
        append_result_to_history(shm_result, run_id, invoke_type, now_str)
        st.session_state.run_count = run_id

    store_last_results(baseline_result, shm_result)
    return baseline_result, shm_result

def invoke_both_lambdas_internal_clicks_only_final(click_count=500):
    """
    One actual button press behaves like multiple internal click-triggered invoke cycles.
    Only the final request result is stored and displayed.
    """
    invoke_type = "Cold Start" if st.session_state.run_count == 0 else "Warm Start"
    run_id = st.session_state.run_count + 1
    now_str = time.strftime("%H:%M:%S")

    baseline_result = None
    shm_result = None

    status_text = st.empty()
    progress_bar = st.progress(0)

    for i in range(click_count):
        status_text.info(f"내부 클릭 이벤트 실행 중... ({i+1}/{click_count})")

        baseline_result = invoke_single_lambda(
            BASELINE_FUNCTION_NAME,
            "Baseline",
            invoke_type
        )
        shm_result = invoke_single_lambda(
            SHM_FUNCTION_NAME,
            "eBPF / Zero-Copy",
            invoke_type
        )

        progress_bar.progress((i + 1) / click_count)

    status_text.success(f"✅ {click_count}회 내부 클릭 이벤트 완료. 마지막 결과만 표시합니다.")
    progress_bar.empty()

    append_result_to_history(baseline_result, run_id, invoke_type, now_str)
    append_result_to_history(shm_result, run_id, invoke_type, now_str)

    st.session_state.run_count = run_id
    store_last_results(baseline_result, shm_result)

    return baseline_result, shm_result

# ---------------------------------------------------------
# 4. UI rendering helpers
# ---------------------------------------------------------
def draw_result_panel():
    baseline_result = st.session_state.last_baseline_result
    shm_result = st.session_state.last_shm_result
    latency_diff = st.session_state.last_latency_diff

    st.subheader("호출 결과")

    if baseline_result:
        if baseline_result["success"]:
            st.success(f"Baseline 호출 성공: {baseline_result['latency_ms']:.2f} ms")
        else:
            st.error(f"Baseline 호출 실패: {baseline_result['error']}")

    if shm_result:
        if shm_result["success"]:
            st.success(f"eBPF / Zero-Copy 호출 성공: {shm_result['latency_ms']:.2f} ms")
        else:
            st.error(f"eBPF / Zero-Copy 호출 실패: {shm_result['error']}")

    if latency_diff is not None:
        st.info(f"지연 시간 차이 (Baseline - eBPF): {latency_diff:.2f} ms")

def draw_json_section():
    baseline_result = st.session_state.last_baseline_result
    shm_result = st.session_state.last_shm_result

    left_json_col, right_json_col = st.columns(2)

    with left_json_col:
        st.markdown("### Baseline JSON")
        if baseline_result is not None:
            st.json(baseline_result.get("result", {}))
        else:
            st.info("아직 Baseline 결과가 없습니다.")

    with right_json_col:
        st.markdown("### eBPF / Zero-Copy JSON")
        if shm_result is not None:
            st.json(shm_result.get("result", {}))
        else:
            st.info("아직 eBPF / Zero-Copy 결과가 없습니다.")

def draw_dashboard(chart_container, table_container):
    if len(st.session_state.history) == 0:
        with chart_container.container():
            st.info("아직 호출 기록이 없습니다.")
        with table_container.container():
            st.info("표시할 데이터가 없습니다.")
        return

    df = pd.DataFrame(st.session_state.history)
    graph_df = df[df["Success"] == True].copy()

    st.session_state.chart_render_count += 1
    st.session_state.table_render_count += 1

    with chart_container.container():
        if len(graph_df) > 0:
            fig = px.line(
                graph_df,
                x="Run",
                y="Latency (ms)",
                color="Series",
                markers=True,
                title=f"Final-request latency after {INTERNAL_CLICK_COUNT} internal click events",
                color_discrete_map={
                    "Baseline": "red",
                    "eBPF / Zero-Copy": "blue"
                }
            )
            fig.update_layout(
                xaxis_title="Batch Run",
                yaxis_title="Latency (ms)"
            )
            st.plotly_chart(
                fig,
                use_container_width=True,
                key=f"latency_chart_{st.session_state.chart_render_count}"
            )

    with table_container.container():
        st.markdown("### 실시간 호출 기록")
        st.dataframe(
            df[[
                "Run",
                "Timestamp",
                "Invoke Type",
                "Series",
                "Latency (ms)",
                "Success",
                "Function Name",
                "Error"
            ]].tail(10),
            use_container_width=True,
            key=f"latency_table_{st.session_state.table_render_count}"
        )

# ---------------------------------------------------------
# 5. Web page UI
# ---------------------------------------------------------
st.title("🚀 Zero-Copy Serverless 최적화 실시간 데모")
st.markdown(
    f"이 대시보드는 버튼을 한 번 누를 때마다 내부적으로 **{INTERNAL_CLICK_COUNT}번의 click-triggered invoke cycle**을 실행하고, "
    f"**마지막 요청의 지연 시간만** 그래프와 표에 표시합니다."
)

col1, col2 = st.columns([1, 2])

with col2:
    chart_placeholder = st.empty()
    table_placeholder = st.empty()

with col1:
    st.subheader("제어 패널")

    if st.button("🔥 단일 호출 (1회)", use_container_width=True):
        with st.spinner("호출 중..."):
            invoke_both_lambdas_once(store_history=True)

    if st.button("🚀 함수 호출 (Invoke)", use_container_width=True):
        with st.spinner(f"{INTERNAL_CLICK_COUNT}회 내부 클릭 이벤트 실행 중..."):
            invoke_both_lambdas_internal_clicks_only_final(click_count=INTERNAL_CLICK_COUNT)

    if st.button("🗑️ 기록 초기화", use_container_width=True):
        st.session_state.history = []
        st.session_state.run_count = 0
        st.session_state.last_baseline_result = None
        st.session_state.last_shm_result = None
        st.session_state.last_latency_diff = None
        st.rerun()

    draw_result_panel()

# Always render once per script run
draw_dashboard(chart_placeholder, table_placeholder)
draw_json_section()
