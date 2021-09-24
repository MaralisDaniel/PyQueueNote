setup:
	@pip install --upgrade pip --no-cache-dir
	@pip install pipenv --user --no-cache-dir
	@pipenv sync

run-dev:
	@pipenv run python3 main.py -d

run-docker:
	@pipenv run python3 main.py -c='config.yaml' -P80 -H='0.0.0.0'

help:
	@pipenv run python3 main.py -h
