import json
import time
import os
import mmap
import pyarrow as pa
import pyarrow.ipc as ipc
from ringbuffer import RingBuffer

# =========================================================
# [Phase 1: Cold Start Init] Zero-copy Shared Memory 읽기
# =========================================================
SHM_ARROW_PATH = "/dev/shm/lambda_arrow_data"
global_routing_table = None

try:
    if os.path.exists(SHM_ARROW_PATH):
        fd = os.open(SHM_ARROW_PATH, os.O_RDONLY)
        # 0을 입력하면 파일의 전체 크기만큼 메모리에 매핑됩니다.
        shm_mmap = mmap.mmap(fd, 0, mmap.MAP_SHARED, mmap.PROT_READ)
        
        # 직렬화 해제(Deserialization) 없이 Arrow 포맷을 그대로 메모리 뷰로 읽어옵니다.
        reader = ipc.RecordBatchFileReader(pa.BufferReader(shm_mmap))
        global_routing_table = reader.read_all()
        print(f"[*] Zero-copy Arrow Data Loaded! (Rows: {global_routing_table.num_rows})")
    else:
        print("[!] Arrow SHM file not found. Running with default configs.")
except Exception as e:
    print(f"[!] Arrow Load Error: {e}")


# =========================================================
# [Phase 2: Lambda Handler] S3 이벤트 처리 및 SHM 쓰기
# =========================================================
def hello_handler(event, context):
    print("SHM Lambda triggered!")
    t0 = time.perf_counter()

    # 기존 모니터링 버퍼 오픈 (SHM Writer)
    rb = RingBuffer()
    t1 = time.perf_counter()

    try:
        payload = json.dumps(event).encode("utf-8")
        t2 = time.perf_counter()

        # 모니터링 이벤트 기록
        rb.write(payload)
        t3 = time.perf_counter()

        record_info = {}
        routing_target = "default_route" # 기본값

        if 'Records' in event and len(event['Records']) > 0:
            record = event['Records'][0]
            bucket = record.get('s3', {}).get('bucket', {}).get('name', 'unknown')
            key = record.get('s3', {}).get('object', {}).get('key', 'unknown')
            record_info = {"bucket": bucket, "key": key}
            print(f"File uploaded to bucket: {bucket}, key: {key}")

            # ---------------------------------------------------------
            # [Zero-copy 활용] 방대한 초기화 데이터에서 필요한 값 즉시 조회
            # ---------------------------------------------------------
            if global_routing_table:
                try:
                    # 예시: Arrow 데이터의 'bucket_name' 열에서 일치하는 인덱스를 찾아 'config_val'을 가져옴
                    # (실제 환경에서는 pyarrow.compute.index 류의 함수를 쓰거나, 딕셔너리로 구조화하여 씁니다)
                    # 여기서는 성능 데모를 위해 첫 번째 열의 첫 번째 값을 바로 가져옵니다.
                    routing_target = global_routing_table.column('config_val')[0].as_py()
                except Exception as e:
                    print(f"Arrow Query Error: {e}")
        else:
            print("No S3 Records found in event")

        t4 = time.perf_counter()

        # 응답 Body에 Zero-copy로 읽어온 값과 처리 시간 메트릭 반환
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'sucess',
                'record_info': record_info,
                'zero_copy_config': routing_target, # SHM에서 0초만에 읽어온 대용량 데이터 결과
                'bytes_written': len(payload),
                'open_buffer_ms': round((t1 - t0) * 1000, 3),
                'serialize_ms': round((t2 - t1) * 1000, 3),
                'write_buffer_ms': round((t3 - t2) * 1000, 3),
                'postprocess_ms': round((t4 - t3) * 1000, 3),
                'handler_total_ms': round((t4 - t0) * 1000, 3)
            })
        }
        
    finally:
        rb.close()
