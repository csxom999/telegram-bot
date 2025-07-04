#!/usr/bin/env bash
# kill mọi process Python đang chạy main.py (phiên cũ)
pkill -f main.py || true

# khởi bot
python main.py

