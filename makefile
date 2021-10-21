setup:
	@pip install --upgrade pip --no-cache-dir
	@pip install -r requirements.txt --user --no-cache-dir

setup-dev:
	@pip install --upgrade pip --no-cache-dir
	@pip install -r requirements-dev.txt --user --no-cache-dir

run-dev:
	@python3 main.py -d

run:
	@python3 main.py -c='config.yaml'

help:
	@python3 main.py -h

test:
	@python3 -m pytest tests -vv --cov=mproxy --cov-report term
