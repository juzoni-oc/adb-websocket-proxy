FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    ADB_HOST=127.0.0.1 \
    ADB_PORT=5037 \
    WS_PORT=8765

WORKDIR /app

# Install Android platform tools (adb) so the proxy can reach local devices.
RUN apt-get update && apt-get install -y --no-install-recommends \
        android-sdk-platform-tools-common curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8765

CMD ["python", "-m", "src.ws_adb_server"]
