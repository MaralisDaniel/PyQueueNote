FROM python:3.9-slim

WORKDIR /mproxy_app

COPY . /mproxy_app

EXPOSE 8080

ENV CONFIG=config.example.yaml

RUN pip3 install --upgrade pip && pip3 install -r requirements.txt

CMD ["sh", "-c", "./mproxy_server.py -c=$CONFIG -H0.0.0.0 -P8080 --debug"]
