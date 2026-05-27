generate-fake-inputs:
	python scripts/generate_fake_inputs.py

clean-fake-inputs:
	python scripts/generate_fake_inputs.py --clean


lint-imports:
	lint-imports

test:
	pytest

cov:
	pytest --cov=src/archive_indexer --cov-branch --cov-report=term-missing:skip-covered --cov-fail-under=90

cov-html:
	pytest --cov=src/archive_indexer --cov-branch --cov-report=html

mutate:
	mutmut run

mutate-browse:
	mutmut browse
