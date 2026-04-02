import pyarrow as pa
import pyarrow.ipc as ipc
import os
from shm_registry import init_registry

SHM_ARROW_PATH = "/dev/shm/lambda_arrow_data"

def bake_data():
    print("[*] 초기화 데이터를 Arrow 포맷으로 굽습니다...")
    data_size = 100000 # 1MB로 임의 지정
    bucket_names = [f"stress-bucket-{i}" for i in range(data_size)]
    config_values = [f"high-perf-cluster-{i}" for i in range(data_size)]
    
    batch = pa.RecordBatch.from_arrays(
        [pa.array(bucket_names), pa.array(config_values)],
        names=['bucket_name', 'config_val']
    )

    fd = os.open(SHM_ARROW_PATH, os.O_CREAT | os.O_RDWR)
    os.ftruncate(fd, 0)
    
    with os.fdopen(fd, 'wb') as f:
        with ipc.new_file(f, batch.schema) as writer:
            writer.write_batch(batch)
            
    print(f"[+] shared memory path 생성 완료: {SHM_ARROW_PATH}")

if __name__ == "__main__":
    # 1. dummy 메타데이터 준비
    bake_data()
    # 2. 전역 인스턴스 레지스트리 초기화
    init_registry()