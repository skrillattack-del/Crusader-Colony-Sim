# Crusader Colony Sim — production image (pure stdlib, no pip installs)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PAWNS=1000 \
    MAP_SIZE=192 \
    DAYS_PER_SEC=15

WORKDIR /app
COPY . .

# Railway injects $PORT; default to 8080 locally
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/api/state',timeout=4)"

CMD python main.py --mode web --host 0.0.0.0 --port ${PORT:-8080} \
    --pawns ${PAWNS} --map-size ${MAP_SIZE}
