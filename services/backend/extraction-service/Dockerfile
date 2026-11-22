FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .

# No pip cache in the image: it is public, and cached package pages (e.g. PyJWT's example token)
# trip the secret scan in publish-images.yml.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY ./ .

EXPOSE 8010

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8010"]