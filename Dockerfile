FROM python:3.9

WORKDIR /srv/mproxy_app

COPY . .

EXPOSE 8080

ENV CONFIG=config.example.yaml
ENV HOST=127.0.0.1
ENV PORT=8080

RUN pip3 install --upgrade pip && pip3 install -r requirements.txt

CMD ["sh", "-c", "python3 m-proxy_server.py -c=$CONFIG -H=$HOST -P=$PORT"]
