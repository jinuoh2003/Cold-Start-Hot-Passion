#!/bin/sh
set -e

echo "[*] Initializing shared memory buffer..."
python3 /var/task/shm_init.py

echo "[*] Starting Lambda runtime..."
exec python3 -m awslambdaric handler.hello_handler
