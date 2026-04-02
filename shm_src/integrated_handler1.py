import json
import time
import pyarrow as pa
import os

# =========================================================
# [Phase 1: Cold Start Init]
# =========================================================
cold_init_t0 = time.perf_counter()

# TODO: 기존 eBPF 초기화 코드 유지
# import bpf_module 
# bpf_module.init_ebpf()  

cold_init_t1 = time.perf_counter()
COLD_INIT_MS = round((cold_init_t1 - cold_init_t0) * 1000, 3)

# =========================================================
# [Phase 2: Lambda Handler]
# Arrow Zero-Copy 매핑 속도 정밀 측정
# =========================================================
def hello_handler(event, context):
    print("SHM Arrow Zero-Copy Lambda triggered!")
    t0 = time.perf_counter()

    # 1. Setup: bake_arrow_shm.py 에서 구워둔 경로 지정
    SHM_PATH = "/dev/shm/lambda_arrow_data"
    t1 = time.perf_counter()

    # 2. 🚨 핵심 구간: Arrow Memory Map을 이용한 Zero-Copy 연결
    try:
        # pa.memory_map('r')는 데이터를 메모리로 복사하지 않습니다!
        mmap_source = pa.memory_map(SHM_PATH, 'r')
        reader = pa.ipc.RecordBatchFileReader(mmap_source)
        
        # 테이블 객체를 만들지만, 실제 데이터는 mmap_source(공유메모리)를 가리킴
        table = reader.read_all() 
        payload_size = table.nbytes
    except Exception as e:
        print(f"WARNING: Arrow SHM read failed - {e}")
        table = None
        payload_size = 0
        mmap_source = None
    t2 = time.perf_counter()

    # 3. Buffer close: 사이즈만 재고 참조 해제
    if mmap_source:
        mmap_source.close()
    t3 = time.perf_counter()

    # 4. Processing
    routing_target = "shm_arrow_zero_copy"
    t4 = time.perf_counter()

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "shm_arrow_zero_copy",
            "payload_size": payload_size,
            
            # SHM 핸들러와 비교용 공통 필드
            "zero_copy_config": routing_target,
            "cold_init_ms": COLD_INIT_MS,

            # 단계별 메트릭 (Arrow 매핑 속도!)
            "setup_ms": round((t1 - t0) * 1000, 3),
            "pure_memory_mapping_ms": round((t2 - t1) * 1000, 3), # 🚨 비교 대상
            "buffer_close_ms": round((t3 - t2) * 1000, 3),
            "process_ms": round((t4 - t3) * 1000, 3),
            "total_ms": round((t4 - t0) * 1000, 3)
        })
    }
