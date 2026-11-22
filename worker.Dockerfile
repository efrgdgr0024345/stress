FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_THREAD_LIMIT=1 PYTHONPATH=/app
WORKDIR /app
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then cp /run/secrets/proxy_ca /usr/local/share/ca-certificates/build-proxy.crt; update-ca-certificates; fi; \
    apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libseccomp2 \
    && rm -rf /var/lib/apt/lists/* /usr/local/share/ca-certificates/build-proxy.crt \
    && update-ca-certificates --fresh
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
COPY packages ./packages
COPY services ./services
COPY RELEASE.json loader.php LESSONS_LEARNED.md ./
COPY scripts/run_pipeline.py scripts/run_pipeline.py
RUN useradd --uid 10001 --create-home worker
USER worker
ENTRYPOINT ["python", "-m", "services.api.extract_worker"]
