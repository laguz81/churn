# Panel de evaluacion ciega A/B - imagen de la app Flask
# Solo incluye codigo de la app. Nunca incluye secreto/, datos/ ni CSV del
# corpus: esos se inyectan en tiempo de ejecucion via volumenes montados
# por docker-compose.yml.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py db.py ./
COPY templates ./templates
COPY static ./static

# Puerto interno HTTP plano; una proxy externa (churn-test.ecticsoft.com)
# termina TLS y reenvia aqui con cabeceras X-Forwarded-*.
EXPOSE 8000

# Nunca --reload, nunca modo debug. gunicorn en produccion dentro del
# contenedor.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "app:app"]
