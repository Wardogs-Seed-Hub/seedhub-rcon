FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY seedhub_rcon/ ./seedhub_rcon/
USER 10001:10001
ENTRYPOINT ["python", "-m", "seedhub_rcon"]
CMD ["serve"]
