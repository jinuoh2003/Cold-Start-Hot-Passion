import json
import time
import urllib.request
import datetime
import hashlib
import hmac
import os
#import boto3

# =========================================================
# [Phase 1: Init (Cold Start)]
cold_init_t0 = time.perf_counter()
cold_init_t1 = time.perf_counter()
COLD_INIT_MS = round((cold_init_t1 - cold_init_t0) * 1000, 3)

# =========================================================
# [1-1. AWS SigV4 signature 생성: AWS boto3를 사용하지 않는 경우, 임의의 인증 헤더 생성 필요]
def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def get_sigv4_headers(host, region, service, method, path):
    access_key = os.environ.get('AWS_ACCESS_KEY_ID', 'test')
    secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY', 'test')
    
    t = datetime.datetime.utcnow()
    amzdate = t.strftime('%Y%m%dT%H%M%SZ')
    datestamp = t.strftime('%Y%m%d')

    # 1. Canonical Request 생성
    canonical_uri = '/' + path
    canonical_headers = f'host:{host}\nx-amz-date:{amzdate}\n'
    signed_headers = 'host;x-amz-date'
    payload_hash = hashlib.sha256(''.encode('utf-8')).hexdigest()
    canonical_request = f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    # 2. String to Sign 생성
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = f"{algorithm}\n{amzdate}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

    # 3. Signature 생성
    kDate = sign(('AWS4' + secret_key).encode('utf-8'), datestamp)
    kRegion = sign(kDate, region)
    kService = sign(kRegion, service)
    kSigning = sign(kService, 'aws4_request')
    signature = hmac.new(kSigning, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    # 4. 인증 헤더 반환
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
def hello_handler(event, context):
    t0 = time.perf_counter()

    # 1. Setup
    bucket = "demo-web-bucket"
    key = "dummy_50mb.txt"
    host = "ministack:4566"
    region = "us-east-1"
    service = "s3"
    
    url = f"http://{host}/{bucket}/{key}"
    routing_target = "baseline_urllib_sigv4"
    
    headers = get_sigv4_headers(host, region, service, 'GET', f"{bucket}/{key}")
    
    t1 = time.perf_counter()

    # 네트워크 통신 및 메모리 복사
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        data = response.read()  # 병목 발생 지점 (pure_memory_copy_ms)
    t2 = time.perf_counter()

    # 3. Buffer Teardown
    payload_size = len(data)
    t3 = time.perf_counter()

    # 4. Processing
    t4 = time.perf_counter()

    # 실행 정보 json
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
