ARG BUILD_FROM
FROM ${BUILD_FROM}
WORKDIR /opt/baiamonte
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
COPY app app
COPY db db
COPY scripts scripts
COPY dashboards dashboards
COPY entrypoint.py /entrypoint.py
EXPOSE 8099 8100 8101
CMD ["python3", "/entrypoint.py"]
