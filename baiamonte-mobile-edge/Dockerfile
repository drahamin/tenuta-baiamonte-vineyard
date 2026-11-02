ARG BUILD_FROM
FROM ${BUILD_FROM}
RUN apk add --no-cache python3 py3-pip curl ca-certificates \
    && curl -fsSL https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-linux-arm64 -o /usr/local/bin/cloudflared \
    && echo '3df43aedc9ff291d1735b5cb576cb97e0b157488796db2e32b28aecabb445775  /usr/local/bin/cloudflared' | sha256sum -c - \
    && chmod 755 /usr/local/bin/cloudflared
WORKDIR /opt/edge
COPY requirements.txt .
RUN pip3 install --break-system-packages --no-cache-dir -r requirements.txt
COPY gateway.py launcher.py ./
CMD ["python3", "launcher.py"]
