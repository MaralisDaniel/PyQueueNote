FROM python:3.9

WORKDIR /srv/mproxy_app

COPY . .

EXPOSE 8080

ENV CONFIG=config.example.yaml
ENV HOST=127.0.0.1
ENV PORT=8080

RUN pip3 install --upgrade pip && pip3 install --no-cache-dir pipenv

RUN pipenv sync

CMD ["sh", "-c", "pipenv run python3 main.py -c=$CONFIG -H=$HOST -P=$PORT"]
