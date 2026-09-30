# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/superintelligenceco/invoice-agent" \
      org.opencontainers.image.description="Invoice extraction and PO matching: web page and HTTP API" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /dist/*.whl /tmp/
RUN whl="$(ls /tmp/*.whl)" && pip install --no-cache-dir "${whl}[api]" && rm -f /tmp/*.whl
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --chown=app:app dataset ./dataset
COPY --chown=app:app examples ./examples
USER app
EXPOSE 8000
ENTRYPOINT ["invoice-agent"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000", "--pos", "dataset/purchase_orders.json", "--receipts", "dataset/receipts.json"]
