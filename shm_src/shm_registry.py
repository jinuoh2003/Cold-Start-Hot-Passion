import os
import mmap
import fcntl
import struct
import time

SHM_REG_PATH = "/dev/shm/lambda_registry"
MAX_INSTANCES = 100
# 레코드 구조 (32바이트): PID(8), 상태(8: 0=Empty, 1=Starting, 2=Warm), 타임스탬프(8), 예비용(8)
RECORD_SIZE = 32 

def init_registry():
    """배포 전: 호스트에서 레지스트리 SHM 파일을 초기화"""
    fd = os.open(SHM_REG_PATH, os.O_CREAT | os.O_RDWR)
    os.ftruncate(fd, 8 + (MAX_INSTANCES * RECORD_SIZE))
    
    # 초기화
    mm = mmap.mmap(fd, 0, mmap.MAP_SHARED, mmap.PROT_WRITE)
    mm.write(b'\x00' * (8 + (MAX_INSTANCES * RECORD_SIZE)))
    mm.close()
    os.close(fd)
    print(f"[*] SHM Registry initialized at {SHM_REG_PATH}")

class InstanceRegistry:
    def __init__(self):
        self.fd = os.open(SHM_REG_PATH, os.O_RDWR)
        self.mm = mmap.mmap(self.fd, 0, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

    def lock(self):
        """동시성 제어: Lock"""
        fcntl.flock(self.fd, fcntl.LOCK_EX)

    def unlock(self):
        fcntl.flock(self.fd, fcntl.LOCK_UN)

    def update_status(self, pid, status):
        """자신의 PID와 상태 (Starting/Warm)를 SHM에 기록"""
        self.lock()
        try:
            empty_slot = -1
            for i in range(MAX_INSTANCES):
                offset = 8 + (i * RECORD_SIZE)
                r_pid, r_status, r_ts, _ = struct.unpack("QQQQ", self.mm[offset:offset+32])
                
                # 기존 PID 업데이트
                if r_pid == pid:
                    self.mm[offset:offset+32] = struct.pack("QQQQ", pid, status, int(time.time()), 0)
                    return
                # 빈 슬롯 찾기
                if r_pid == 0 and empty_slot == -1:
                    empty_slot = offset
            
            # 새 인스턴스 등록
            if empty_slot != -1:
                self.mm[empty_slot:empty_slot+32] = struct.pack("QQQQ", pid, status, int(time.time()), 0)
                # 활성 카운트 증가
                self.mm.seek(0)
                active_count = struct.unpack("Q", self.mm.read(8))[0]
                self.mm[:8] = struct.pack("Q", active_count + 1)
        finally:
            self.unlock()

    def get_warm_count(self):
        self.lock()
        try:
            self.mm.seek(0)
            return struct.unpack("Q", self.mm.read(8))[0]
        finally:
            self.unlock()

    def close(self):
        self.mm.close()
        os.close(self.fd)