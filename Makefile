.PHONY: help install test run webui telegram clean lint format

help:
	@echo "Scrutator Makefile targets:"
	@echo "  install  - Install the package and dependencies"
	@echo "  test     - Run pytest with coverage"
	@echo "  run      - Run the CLI (use with query argument)"
	@echo "  webui    - Launch the Gradio web interface"
	@echo "  telegram - Start the Telegram bot"
	@echo "  lint     - Run ruff linter"
	@echo "  format   - Run black formatter"
	@echo "  clean    - Remove generated files"

install:
	pip install -e .
	pip install -r requirements.txt
	@echo "✅ Installation complete."

test:
	pytest tests/ --cov=core --cov=memory -v

run:
	python -m api.cli $(filter-out $@,$(MAKECMDGOALS))

webui:
	python -m api.web_ui

telegram:
	python -m api.telegram_bot

lint:
	ruff check .

format:
	black .

clean:
	rm -rf reports/*.md
	rm -rf logs/*.log
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .mypy_cache
	rm -rf __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} \;

%:
	@# Pass unrecognized targets as arguments to 'run'
	@:
