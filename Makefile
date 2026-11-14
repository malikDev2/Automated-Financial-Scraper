.PHONY: install test run-local backfill-local docker-up docker-down bootstrap

install:
	pip install -r requirements-dev.txt
	pip install -e . 2>/dev/null || true

test:
	PYTHONPATH=src pytest -q

# Offline demo: synthetic prices, local Parquet lake, no AWS/Snowflake needed
run-local:
	PYTHONPATH=src PRICE_PROVIDER=synthetic LOAD_TARGET=local LOAD_SNOWFLAKE=false python -m fin_scraper run

backfill-local:
	PYTHONPATH=src PRICE_PROVIDER=synthetic LOAD_TARGET=local LOAD_SNOWFLAKE=false \
	python -m fin_scraper backfill --start 2024-06-03 --end 2024-06-14

bootstrap:
	PYTHONPATH=src python -m fin_scraper bootstrap

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
