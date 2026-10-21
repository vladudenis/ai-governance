FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY frontend ./frontend
COPY alembic ./alembic
COPY .streamlit ./.streamlit
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000 8501

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
