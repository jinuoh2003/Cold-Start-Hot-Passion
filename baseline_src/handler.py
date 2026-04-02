import json
import time
import urllib.request
import datetime
import hashlib
import hmac
import os

# =========================================================
# [Phase 1: Cold Start Init]
# boto3를 완전히 버렸기 때문에 이 구간은 0ms에 가깝게 측정됩니다.
# =========================================================
cold_init_t0 = time.perf_counter()

# 내장 라이브러리만 사용하므로 무거운 초기화 오버헤드가 증발합니다.
# eBPF 모듈 로드가 필요하다면 여기서 수행 (현재는 순수 Baseline 비교를 위해 생략)

cold_init_t1 = time.perf_counter()
COLD_INIT_MS = round((cold_init_t1 - cold_init_t0) * 1000, 3)

# =========================================================
# [Helper: 수제 AWS SigV4 서명 생성기]
# =========================================================
def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def get_sigv4_headers(host, region, service, method, path):
    """boto3 없이 AWS SigV4 인증 헤더를 직접 생성하는 경량 함수"""
    access_key = os.environ.get('AWS_ACCESS_KEY_ID', 'test')
    secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY', 'test')
    
    t = datetime.datetime.utcnow()
    amzdate = t.strftime('%Y%m%dT%H%M%SZ')
    datestamp = t.strftime('%Y%m%d')

    # 1. Canonical Request 생성 (단순화 버전)
    canonical_uri = '/' + path
    canonical_headers = f'host:{host}\nx-amz-date:{amzdate}\n'
    signed_headers = 'host;x-amz-date'
    payload_hash = hashlib.sha256(''.encode('utf-8')).hexdigest()
    canonical_request = f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    # 2. String to Sign 생성
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = f"{algorithm}\n{amzdate}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

    # 3. 서명(Signature) 계산
    kDate = sign(('AWS4' + secret_key).encode('utf-8'), datestamp)
    kRegion = sign(kDate, region)
    kService = sign(kRegion, service)
    kSigning = sign(kService, 'aws4_request')
    signature = hmac.new(kSigning, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    # 4. 최종 인증 헤더 반환
    authorization_header = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    
    return {
        'x-amz-date': amzdate,
        'Authorization': authorization_header
    }

# =========================================================
# [Phase 2: Lambda Handler]
# =========================================================
def hello_handler(event, context):
    t0 = time.perf_counter()

    # 1. Setup: S3 URL 및 헤더 준비 (CPU 오버헤드 미미함)
    bucket = "demo-web-bucket"
    key = "dummy_50mb.txt"
    host = "ministack:4566"
    region = "us-east-1"
    service = "s3"
    
    url = f"http://{host}/{bucket}/{key}"
    routing_target = "baseline_urllib_sigv4"
    
    # 수제 SigV4 헤더 생성 (boto3를 대체하는 핵심 로직)
    headers = get_sigv4_headers(host, region, service, 'GET', f"{bucket}/{key}")
    
    t1 = time.perf_counter()

    # 2. 🚨 핵심 구간: 네트워크 통신 및 "물리적 메모리 복사"
    # boto3의 무거움은 피했지만, "데이터를 네트워크로 복사해오는 본질적 한계"는 피할 수 없음
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        data = response.read()  # <--- 병목 발생 지점 (pure_memory_copy_ms)
    t2 = time.perf_counter()

    # 3. Buffer Teardown
    payload_size = len(data)
    t3 = time.perf_counter()

    # 4. Processing
    t4 = time.perf_counter()

    # SHM(Zero-Copy) 출력 형식과 100% 동일한 스키마 반환
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "baseline_urllib_sigv4",
            "payload_size": payload_size,
            "zero_copy_config": routing_target,
            "cold_init_ms": COLD_INIT_MS,
            
            # 단계별 메트릭
            "setup_ms": round((t1 - t0) * 1000, 3),
            "pure_memory_copy_ms": round((t2 - t1) * 1000, 3),    # 데이터 크기에 비례하여 증가
            "pure_memory_mapping_ms": 0.0,                        # SHM과 비교용 (항상 0)
            "buffer_teardown_ms": round((t3 - t2) * 1000, 3),  
            "process_ms": round((t4 - t3) * 1000, 3),
            "total_ms": round((t4 - t0) * 1000, 3)
        })
    }
