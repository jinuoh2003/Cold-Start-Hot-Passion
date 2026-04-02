import sys
import os
import struct
import sys
from bcc import BPF

# 1. 경로 설정: 현재 파일의 위치를 기준으로 shm_src 폴더 탐색
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHM_SRC_PATH = os.path.join(CURRENT_DIR, "shm_src")
sys.path.append(SHM_SRC_PATH)

try:
    from shm_registry import InstanceRegistry
except ImportError:
    print(f"[!] Error: shm_registry.py를 {SHM_SRC_PATH}에서 찾을 수 없습니다.")
    sys.exit(1)

# 2. eBPF C 코드 (헤더 충돌 방지 로직 포함)
bpf_text = """
#define KBUILD_MODNAME "lambda_monitor"
#include <linux/ptrace.h>
#include <linux/sched.h>

struct data_t {
    u64 pid;
    char comm[16];
};

BPF_PERF_OUTPUT(events);

// execve 시스템 콜이 완료되는 시점이 아니라 시작되는 시점에 낚아챕니다.
int kprobe__sys_execve(struct pt_regs *ctx) {
    struct data_t data = {};
    
    // 현재 프로세스의 PID (TGID) 가져오기
    u64 pid_tgid = bpf_get_current_pid_tgid();
    data.pid = pid_tgid >> 32;
    
    // 프로세스 이름 가져오기
    bpf_get_current_comm(&data.comm, sizeof(data.comm));
    
    // 'python'으로 시작하는 프로세스만 필터링 (람다 런타임)
    if (data.comm[0] == 'p' && data.comm[1] == 'y' && data.comm[2] == 't') {
        events.perf_submit(ctx, &data, sizeof(data));
    }
    return 0;
}
"""

def main():
    # eBPF는 루트 권한 필요
    if os.geteuid() != 0:
        print("[!] Error: eBPF를 실행하려면 sudo 권한이 필요합니다.")
        sys.exit(1)

    print("[*] eBPF Pre-emptive Warming Daemon 실행 중...")
    print("[*] 람다 컨테이너(Python)의 생성을 감지하여 공유 메모리에 즉시 등록합니다.")
    
    try:
        # BPF 컴파일 및 로드
        b = BPF(text=bpf_text)
        registry = InstanceRegistry()
        
        def print_event(cpu, data, size):
            event = b["events"].event(data)
            pid = event.pid
            comm = event.comm.decode('utf-8', 'replace')
            
            # 커널 레벨에서 감지하자마자 SHM Registry에 'STARTING(1)'으로 등록
            registry.update_status(pid, status=1)
            print(f"  >> [eBPF Detect] PID: {pid} ({comm}) -> SHM Registry Marked as STARTING")

        b["events"].open_perf_buffer(print_event)
        
        print("[+] 모니터링 시작. (종료: Ctrl+C)")
        while True:
            b.perf_buffer_poll()
            
    except Exception as e:
        print(f"[!] BPF Error: {e}")
        if "address_space" in str(e):
            print("[i] 힌트: 커널 헤더 충돌은 보통 무시해도 되지만, 에러가 지속되면 헤더 패키지를 재설치하세요.")
    except KeyboardInterrupt:
        print("\n[*] 데몬을 종료합니다.")
    finally:
        if 'registry' in locals():
            registry.close()

if __name__ == "__main__":
    main()