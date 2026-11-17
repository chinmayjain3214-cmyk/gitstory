# gitstory as a public website. Used by Render (see render.yaml), and works on
# any host that runs containers and sets $PORT.
FROM python:3.12-slim

# git is the only thing gitstory needs besides Python.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY gitstory ./gitstory
RUN pip install --no-cache-dir . && useradd --create-home gitstory

USER gitstory
ENV PYTHONUNBUFFERED=1 \
    PORT=10000
EXPOSE 10000

# --public: listen on 0.0.0.0:$PORT, accept the site's own address, and apply
# the limits in gitstory/server.py (Limits.public), adjustable with env vars.
CMD ["gitstory", "--serve", "--public"]
