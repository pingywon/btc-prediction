FROM python:3-slim

WORKDIR /app
COPY app.py index.html fluid.html ticket.html algo.html README.md ./

ENV PORT=80 \
    BIND=0.0.0.0 \
    BP_DB=/data/data.db

RUN mkdir -p /data
VOLUME /data

EXPOSE 80

CMD ["python3", "app.py"]
