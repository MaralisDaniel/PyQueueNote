FROM python:3.9.7-bullseye

WORKDIR ~/app

COPY . .

RUN pip3 install --upgrade pip && pip3 install --no-cache-dir pipenv

RUN pipenv sync

CMD ["make", "run-docker"]
