# CampusLink portal (TV3). Image chay ca ROLE=portal va (sau nay) ROLE=worker (SRS 4.6).
# Base khoa bang digest OCI index (C-04, NFR-14): python 3.12.16-slim-trixie, imagetools inspect 2026-11-17, TV3
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
# Font co dau tieng Viet cho PDF the QR
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY portal ./portal
RUN useradd -r -u 1002 portal && mkdir -p /data/qr && chown portal /data/qr
USER portal
ENV PORTAL_PORT=8081
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=5s --retries=18 CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ.get('PORTAL_PORT','8081'),timeout=4)"
CMD ["python", "-m", "portal"]
