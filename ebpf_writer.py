from bcc import BPF
import os
import struct
from shm_registry import InstanceRegistry

# eBPF C 코드: execve를 추적하여 'python' 명령어가 실행될 때 이벤트 전송
bpf_text = """
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

BPF_PERF_OUTPUT(events);

struct data_t {
    u64 pid;
    char comm[16];
};

int kprobe__sys_execve(struct pt_regs *ctx) {
    struct data_t data = {};
    data.pid = bpf_get_current_pid_tgid() >> 32;
    bpf_get_current_comm(&data.comm, sizeof(data.comm));
    
    // 'python' 프로세스(람다 런타임) 시작 감지
    if (data.comm[0] == 'p' && data.comm[1] == 'y') {
        events.perf_submit(ctx, &data, sizeof(data));
    }
    return 0;
}
"""

def main():
    print("[*] eBPF Pre-emptive Warming Daemon 실행 중... (Ctrl+C로 종료)")
    b = BPF(text=bpf_text)
    
    # Python 레벨의 공유 메모리 레지스트리 연결
    registry = InstanceRegistry()

    def print_event(cpu, data, size):
        event = b["events"].event(data)
        pid = event.pid
        comm = event.comm.decode('utf-8', 'replace')
        
        # 커널이 람다 컨테이너의 시작을 감지하면 SHM 레지스트리에 STARTING 상태 즉시 기록
        print(f"[eBPF] 컨테이너 시작 감지! PID: {pid} ({comm}) -> SHM Registry 사전 등록 중...")
        registry.update_status(pid, status=1) # 1 = STARTING 상태

    b["events"].open_perf_buffer(print_event)
    
    try:
        while True:
            b.perf_buffer_poll()
    except KeyboardInterrupt:
        print("\n[*] 종료 중...")
        registry.close()

if __name__ == "__main__":
    main()