ARG BUILD_FROM
FROM ${BUILD_FROM}
WORKDIR /opt/baiamonte
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
RUN apk add --no-cache nodejs npm git curl ffmpeg poppler-utils
COPY system_whatsapp/package.json system_whatsapp/package-lock.json system_whatsapp/
RUN cd system_whatsapp && npm ci --omit=dev --no-audit --no-fund
COPY config.yaml config.yaml
COPY icon.png icon.png
COPY app app
COPY icon.png app/static/icon.png
COPY docs docs
COPY db db
RUN mkdir -p scripts
COPY scripts/dashboard_manager.py scripts/dashboard_manager.py
COPY scripts/integration_manager.py scripts/integration_manager.py
COPY scripts/audit_live_integrity.sh scripts/audit_live_integrity.sh
COPY dashboards dashboards
COPY custom_components custom_components
COPY system_whatsapp system_whatsapp
COPY entrypoint.py /entrypoint.py
EXPOSE 8099 8100 8101
CMD ["python3", "/entrypoint.py"]
