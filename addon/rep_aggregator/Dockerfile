FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    REPAGG_DATA=/data \
    REPAGG_STATIC=/app/web

WORKDIR /app
COPY backend/ /app/backend/
RUN pip install --no-cache-dir /app/backend
# Frontend is built on the Mac; the Pi only copies it.
COPY web/ /app/web/
# Genuine reference photos (rolex.com), registered into /data on start.
COPY genuine/ /app/genuine/
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
