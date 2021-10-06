setup:
	@pip install --upgrade pip --no-cache-dir
	@pip install pipenv --user --no-cache-dir
	@pipenv sync

run-dev:
	@pipenv run python3 main.py -d

run-prod:
	@pipenv run python3 main.py -c='config.yaml'

help:
	@pipenv run python3 main.py -h
