FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# native libs WeasyPrint needs for Markdown -> PDF rendering (cairo/pango/gdk-pixbuf) -
# cache-mounted so apt doesn't re-download on every build either. Both mounts are
# excluded from the final image automatically, so no rm -rf cleanup needed here.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-cffi libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info

WORKDIR /app
COPY requirements.txt .
# cache mount persists uv's download/wheel cache across builds without baking
# it into the image - same installed packages, same final layers, much faster
# on repeat builds since requirements.txt hasn't changed
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

COPY app.py .
COPY librarian.py .
COPY notifications.py .
COPY watcher.py .
COPY reports.py .
COPY toolsets/ toolsets/
COPY toolsets.yaml .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
