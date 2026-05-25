FROM python:3.12-slim

WORKDIR /app

# shared package must be copied before installing requirements
# (build context is repo root — set in docker-compose.yml)
COPY shared/ ./shared/

COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ .

# /app is on PYTHONPATH so both `shared` and `app` packages are importable
ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
