FROM node:24-alpine AS web
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --strict-ssl=true --no-audit --no-fund
COPY tsconfig.json vite.config.ts ./
COPY apps ./apps
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 CAESAR_DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
COPY --chown=10001:10001 packages ./packages
COPY --chown=10001:10001 services ./services
COPY --chown=10001:10001 loader.php LESSONS_LEARNED.md ./
COPY --from=web --chown=10001:10001 /app/dist ./dist
RUN useradd --uid 10001 --create-home caesar && mkdir /app/data && chown caesar:caesar /app/data
USER caesar
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8000/api/v1/health').status == 200"
CMD ["python", "-m", "uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
