import os
import mmap

SHM_PATH = "/dev/shm/lambda_ringbuf"
BUF_SIZE = 1024 * 1024  # 1MB

def init_buffer():
    fd = os.open(SHM_PATH, os.O_CREAT | os.O_RDWR)
    os.ftruncate(fd, BUF_SIZE)

    buf = mmap.mmap(fd, BUF_SIZE, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)

    buf[0:8] = (0).to_bytes(8, "little")
    buf[8:16] = (0).to_bytes(8, "little")

    buf.flush()
    buf.close()
    os.close(fd)

    print(f"Initialized shared memory ring buffer at {SHM_PATH}")

if __name__ == "__main__":
    init_buffer()
