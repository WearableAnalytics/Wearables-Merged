FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install .

COPY ./ .

EXPOSE 8010

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8010"]