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

# 실제 배포된 함수 이름으로 바꿔주세요
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

    # JSON이 아닌 일반 문자열인 경우
    if parsed is None:
        return {"raw_response": raw_text}

    # API Gateway 스타일 응답 처리
    # 예: {"statusCode": 200, "body": "{\"message\":\"ok\"}"}
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
                    "object": {"key": "test.txt"}
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
            "error": f"함수 '{function_name}'를 찾을 수 없습니다. 상세: {err}",
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
                "error": f"Lambda 실행 오류: {function_error}",
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
            "error": f"예상치 못한 오류: {e}",
            "latency_ms": 0,
            "result": {}
        }

def invoke_both_lambdas():
    invoke_type = "Cold Start" if st.session_state.run_count == 0 else "Warm Start"
    run_id = st.session_state.run_count + 1
    now_str = time.strftime("%H:%M:%S")

    baseline_result = invoke_single_lambda(
        function_name=BASELINE_FUNCTION_NAME,
        series_name="Baseline",
        invoke_type=invoke_type
    )

    shm_result = invoke_single_lambda(
        function_name=SHM_FUNCTION_NAME,
        series_name="eBPF / Zero-Copy",
        invoke_type=invoke_type
    )

    # history에 각각 따로 저장
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
# 3. 웹 페이지 UI
# ---------------------------------------------------------
st.title("🚀 Zero-Copy Serverless 최적화 데모")
st.markdown("""
이 대시보드는 **Baseline 방식**과 **eBPF / Shared Memory 방식**을 동시에 호출하여  
호출 지연 시간을 비교 시각화합니다.
""")

with st.expander("현재 설정", expanded=False):
    st.write(f"Baseline function: `{BASELINE_FUNCTION_NAME}`")
    st.write(f"eBPF/SHM function: `{SHM_FUNCTION_NAME}`")

# ---------------------------------------------------------
# 4. 제어 패널 + 결과 출력
# ---------------------------------------------------------
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("제어 패널")

    if st.button("🔥 함수 호출 (Invoke)", use_container_width=True):
        with st.spinner("두 함수를 호출하는 중..."):
            baseline_result, shm_result = invoke_both_lambdas()

            st.markdown("### 호출 결과")

            if baseline_result["success"]:
                st.success(f"Baseline 호출 성공: **{baseline_result['latency_ms']:.2f} ms**")
            else:
                st.error(f"Baseline 호출 실패: {baseline_result['error']}")

            if shm_result["success"]:
                st.success(f"eBPF / Zero-Copy 호출 성공: **{shm_result['latency_ms']:.2f} ms**")
            else:
                st.error(f"eBPF / Zero-Copy 호출 실패: {shm_result['error']}")

            if baseline_result["success"] and shm_result["success"]:
                diff = baseline_result["latency_ms"] - shm_result["latency_ms"]
                st.info(f"지연 시간 차이(Baseline - eBPF): **{diff:.2f} ms**")

            json_col1, json_col2 = st.columns(2)

            with json_col1:
                st.markdown("#### Baseline JSON")
                st.json(baseline_result["result"])

            with json_col2:
                st.markdown("#### eBPF / Zero-Copy JSON")
                st.json(shm_result["result"])

    if st.button("🗑️ 기록 초기화 (Clear)", use_container_width=True):
        st.session_state.history = []
        st.session_state.run_count = 0
        st.rerun()

with col2:
    st.subheader("실시간 지연 시간 비교")

    if len(st.session_state.history) > 0:
        df = pd.DataFrame(st.session_state.history)

        # 성공한 호출만 그래프에 표시
        graph_df = df[df["Success"] == True].copy()

        if len(graph_df) > 0:
            fig = px.line(
                graph_df,
                x="Run",
                y="Latency (ms)",
                color="Series",
                markers=True,
                title="Baseline vs eBPF / Zero-Copy 지연 시간 비교",
                color_discrete_map={
                    "Baseline": "red",
                    "eBPF / Zero-Copy": "blue"
                },
                hover_data=["Timestamp", "Invoke Type", "Function Name"]
            )
            fig.update_layout(
                xaxis_title="호출 횟수",
                yaxis_title="지연 시간 (ms)",
                legend_title="비교 대상"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("성공한 호출 데이터가 없어 그래프를 그릴 수 없습니다.")

        st.markdown("### 호출 기록")
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
            ]],
            use_container_width=True
        )

        # 비교용 Pivot 테이블
        pivot_df = df[df["Success"] == True].pivot_table(
            index=["Run", "Timestamp", "Invoke Type"],
            columns="Series",
            values="Latency (ms)",
            aggfunc="first"
        ).reset_index()

        if "Baseline" in pivot_df.columns and "eBPF / Zero-Copy" in pivot_df.columns:
            pivot_df["개선량 (ms)"] = pivot_df["Baseline"] - pivot_df["eBPF / Zero-Copy"]

        st.markdown("### 비교 요약")
        st.dataframe(pivot_df, use_container_width=True)

    else:
        st.info("왼쪽 패널에서 '함수 호출' 버튼을 눌러 테스트를 시작하세요.")
