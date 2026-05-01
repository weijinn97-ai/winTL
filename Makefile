.PHONY: help install smoke run clean

help:
	@echo "Targets:"
	@echo "  install   Tạo .venv + cài dependencies"
	@echo "  smoke     Chạy smoke test (kiểm tra setup)"
	@echo "  run       Chạy bot"
	@echo "  clean     Xóa .venv + smoke_capture.png + speed_log.csv"

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && \
		pip install opencv-python numpy python-dotenv keyboard

smoke:
	. .venv/bin/activate && python test_smoke.py

run:
	. .venv/bin/activate && python bottlll.py

clean:
	rm -rf .venv smoke_capture.png speed_log.csv __pycache__
