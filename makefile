sync:
	@pipenv sync

sync-dev:
	@pipenv sync --dev

sync-n-test:
	sync-dev
	@pipenv run pytest tests -vv --cov=mproxy --cov-report term

sync-n-test-cov:
	sync-dev
	@pipenv run pytest tests -vv --cov=mproxy --cov-report html

sync-n-run:
	sync
	@pipenv run main.py -c='config.yaml'

sync-n-run-debug:
	sync
	@pipenv run main.py -c='config.yaml' -d

setup:
	@pip install --upgrade pip --no-cache-dir
	@pip install -r requirements.txt --user --no-cache-dir

setup-dev:
	@pip install --upgrade pip --no-cache-dir
	@pip install -r requirements-dev.txt --user --no-cache-dir

setup-n-test:
	setup-dev
	@python3 -m pytest tests -vv --cov=mproxy --cov-report term

setup-n-test-cov:
	setup-dev
	@python3 -m pytest tests -vv --cov=mproxy --cov-report term

setup-n-run-debug:
	setup
	@python3 main.py -c='config.yaml' -d

setup-n-run:
	setup
	@python3 main.py -c='config.yaml'

help:
	@python3 main.py -h

full-help:
	@python3 main.py -h
	@python3 main.py --show_queues --show_workers
