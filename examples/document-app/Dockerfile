FROM python:3.12.12-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py smoke.py ./
RUN mkdir /uploads && chown 10001:10001 /uploads
USER 10001:10001
CMD ["python", "app.py", "serve"]
