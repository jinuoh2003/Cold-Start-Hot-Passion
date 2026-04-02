# bake_arrow_shm.py (호스트 머신에서 람다 배포 전 1회 실행)
import pyarrow as pa
import pyarrow.ipc as ipc
import os

SHM_PATH = "/dev/shm/lambda_arrow_data"

def bake_data():
    print("[*] 1MB 상당의 더미 초기화 데이터를 Arrow 포맷으로 굽습니다...")
    
    # 약 10만 줄의 가상 데이터 생성 (DB 라우팅 테이블이라고 가정)
    data_size = 100000
    bucket_names = [f"stress-bucket-{i}" for i in range(data_size)]
    config_values = [f"us-east-cluster-{i}" for i in range(data_size)]
    
    # Arrow RecordBatch(테이블) 생성
    batch = pa.RecordBatch.from_arrays(
        [pa.array(bucket_names), pa.array(config_values)],
        names=['bucket_name', 'config_val']
    )

    # /dev/shm 파일에 IPC 포맷으로 기록
    fd = os.open(SHM_PATH, os.O_CREAT | os.O_RDWR)
    os.ftruncate(fd, 0)
    
    with os.fdopen(fd, 'wb') as f:
        with ipc.new_file(f, batch.schema) as writer:
            writer.write_batch(batch)
            
    print(f"[+] Arrow 데이터 생성 완료: {SHM_PATH}")

if __name__ == "__main__":
    bake_data()
