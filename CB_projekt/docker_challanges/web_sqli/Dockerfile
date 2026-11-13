FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRODUCTS_DB_PATH=/tmp/products.db
RUN pip install --no-cache-dir "Flask>=3.1,<4" \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin ctfuser
COPY --chown=ctfuser:ctfuser app.py .
USER 10001:10001
EXPOSE 7000
CMD ["python", "app.py"]
