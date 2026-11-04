FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py smoke.py probe.py ./
RUN mkdir /uploads && chown 10001:10001 /uploads
USER 10001:10001
CMD ["python", "app.py", "serve"]
