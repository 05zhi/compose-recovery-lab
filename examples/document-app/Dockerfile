FROM python:3.12.12-slim-trixie@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c
# glibc >= 2.41 retains environment arrays during concurrent getenv/setenv.
# Chromium startup can query gettext LANGUAGE on a worker while mutating env.
RUN python -c "import os; assert tuple(map(int, os.confstr('CS_GNU_LIBC_VERSION').split()[1].split('.'))) >= (2, 41)"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw
RUN python -m playwright install --with-deps chromium --only-shell
COPY app.py smoke.py probe.py probe_diagnostics.py browser_smoke.py ui.html ./
RUN mkdir /uploads && chown 10001:10001 /uploads
USER 10001:10001
CMD ["python", "app.py", "serve"]
