FROM python:3.12-slim

WORKDIR /app

COPY shared/ ./shared/

COPY bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
