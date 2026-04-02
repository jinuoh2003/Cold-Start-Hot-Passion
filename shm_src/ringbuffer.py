import os
import mmap

SHM_PATH = "/dev/shm/lambda_ringbuf"
BUF_SIZE = 1024 * 1024
META_SIZE = 16
DATA_START = META_SIZE

class RingBuffer:
    def __init__(self):
        fd = os.open(SHM_PATH, os.O_RDWR)
        self.fd = fd
        self.buf = mmap.mmap(fd, BUF_SIZE, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)

    def close(self):
        self.buf.close()
        os.close(self.fd)

    def _get_head(self):
        return int.from_bytes(self.buf[0:8], "little")

    def _get_tail(self):
        return int.from_bytes(self.buf[8:16], "little")

    def _set_head(self, val):
        self.buf[0:8] = val.to_bytes(8, "little")

    def _set_tail(self, val):
        self.buf[8:16] = val.to_bytes(8, "little")

    def write(self, data: bytes):
        head = self._get_head()
        tail = self._get_tail()

        capacity = BUF_SIZE - DATA_START
        used = head - tail
        free_space = capacity - used

        needed = 4 + len(data)
        if needed > free_space:
            raise RuntimeError("Ring buffer full")

        pos = DATA_START + (head % capacity)

        # 단순 버전: wrap-around 미구현
        if pos + needed > BUF_SIZE:
            raise RuntimeError("Wrap-around not implemented")

        self.buf[pos:pos+4] = len(data).to_bytes(4, "little")
        self.buf[pos+4:pos+4+len(data)] = data

        self._set_head(head + needed)
        self.buf.flush()

    def read(self):
        head = self._get_head()
        tail = self._get_tail()

        if tail >= head:
            return None

        capacity = BUF_SIZE - DATA_START
        pos = DATA_START + (tail % capacity)

        if pos + 4 > BUF_SIZE:
            return None

        length = int.from_bytes(self.buf[pos:pos+4], "little")
        if pos + 4 + length > BUF_SIZE:
            return None

        data = self.buf[pos+4:pos+4+length]
        self._set_tail(tail + 4 + length)
        self.buf.flush()
        return bytes(data)
