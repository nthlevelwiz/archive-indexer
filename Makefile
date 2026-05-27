generate-fake-inputs:
	python scripts/generate_fake_inputs.py

clean-fake-inputs:
	python scripts/generate_fake_inputs.py --clean


lint-imports:
	lint-imports
