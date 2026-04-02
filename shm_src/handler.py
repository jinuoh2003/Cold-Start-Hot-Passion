import json
import time
import os
import mmap
import pyarrow as pa
import pyarrow.ipc as ipc
from shm_registry import InstanceRegistry

# =========================================================
# [Phase 1: Cold Start Init] 
cold_init_t0 = time.perf_counter()

SHM_ARROW_PATH = "/dev/shm/lambda_arrow_data"
global_routing_table = None
my_pid = os.getpid()

# 1. 레지스트리에 내 상태 등록 (Locking 적용)
try:
    registry = InstanceRegistry()
    registry.update_status(my_pid, status=2) # 람다가 시작될 때 레지스트리를 확인하여 자신의 상태를 WARM(2)으로 등록
    warm_instances = registry.get_warm_count()
    print(f"[*] Registered as WARM. Total Active Lambdas: {warm_instances}")
except Exception as e:
    print(f"[!] Registry Update Error: {e}")

# 2. Zero-copy 매핑
try:
    if os.path.exists(SHM_ARROW_PATH):
        mmap_source = pa.memory_map(SHM_ARROW_PATH, 'r')
        reader = ipc.RecordBatchFileReader(mmap_source)
        global_routing_table = reader.read_all()
except Exception as e:
    print(f"[!] Arrow Load Error: {e}")

cold_init_t1 = time.perf_counter()
COLD_INIT_MS = round((cold_init_t1 - cold_init_t0) * 1000, 3)

# =========================================================
# [Phase 2: Lambda Handler]
def hello_handler(event, context):
    t0 = time.perf_counter()
    routing_target = "default_routing"

    if global_routing_table:
        try:
            # SHM에서 즉시 데이터 로드
            routing_target = global_routing_table.column('config_val')[0].as_py()
        except Exception as e:
            print(f"Arrow Query Error: {e}")

    t1 = time.perf_counter()

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "shm_global_registry_success",
            "pid": my_pid,
            "cold_init_ms": COLD_INIT_MS,
            "zero_copy_config": routing_target,
            "process_ms": round((t1 - t0) * 1000, 3)
        })
    }