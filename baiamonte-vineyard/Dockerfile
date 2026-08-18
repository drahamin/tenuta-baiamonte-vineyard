ARG BUILD_FROM
FROM ${BUILD_FROM}
WORKDIR /opt/baiamonte
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
RUN apk add --no-cache nodejs npm git
COPY system_whatsapp/package.json system_whatsapp/package.json
RUN cd system_whatsapp && npm install --omit=dev --no-audit --no-fund
COPY config.yaml config.yaml
COPY icon.png icon.png
COPY app app
COPY icon.png app/static/icon.png
COPY db db
COPY scripts scripts
COPY dashboards dashboards
COPY custom_components custom_components
COPY system_whatsapp system_whatsapp
COPY entrypoint.py /entrypoint.py
EXPOSE 8099 8100 8101
CMD ["python3", "/entrypoint.py"]
