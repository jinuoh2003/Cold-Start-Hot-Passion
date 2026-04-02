# ebpf_writer.py (sudo python3 ebpf_writer.py 로 실행)
from bcc import BPF
import mmap
import os
import struct
import time

# eBPF C 코드 (모든 execve 시스템 콜 추적)
bpf_text = """
#include <uapi/linux/ptrace.h>
BPF_PERF_OUTPUT(events);
int kprobe__sys_execve(struct pt_regs *ctx) {
    u64 pid = bpf_get_current_pid_tgid();
    events.perf_submit(ctx, &pid, sizeof(pid));
    return 0;
}
"""

SHM_PATH = "/dev/shm/lambda_ringbuf"
BUF_SIZE = 1024 * 1024

def main():
    print("[*] eBPF Writer 실행 중... (Ctrl+C로 종료)")
    b = BPF(text=bpf_text)
    
    # SHM 파일 열기
    fd = os.open(SHM_PATH, os.O_RDWR)
    mm = mmap.mmap(fd, BUF_SIZE, mmap.MAP_SHARED, mmap.PROT_WRITE)
    
    def callback(cpu, data, size):
        # 이벤트가 들어오면 Tail 포인터(8~15바이트)를 10바이트씩 증가시킴 (가짜 Delta 생성)
        mm.seek(8)
        current_tail = struct.unpack("<Q", mm.read(8))[0]
        new_tail = current_tail + 10
        mm.seek(8)
        mm.write(struct.pack("<Q", new_tail))
        # print(f"Event captured! New Tail: {new_tail}")

    b["events"].open_perf_buffer(callback)
    
    try:
        while True:
            b.perf_buffer_poll()
    except KeyboardInterrupt:
        mm.close()
        os.close(fd)

if __name__ == "__main__":
    main()
