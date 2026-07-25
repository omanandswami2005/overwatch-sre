# Extends the official HolmesGPT image instead of building from source —
# see README.md "Why the extended image, not a source build".
FROM robustadev/holmes:0.36.0

USER root
# base image is missing the docker CLI, which the built-in docker/core
# toolset shells out to (docker ps / docker logs / docker inspect / ...).
RUN apk add --no-cache docker-cli

# uv, not pip — see README.md tech stack.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY app.py .
COPY holmes-config.yaml /root/.holmes/config.yaml

# base image's ENTRYPOINT runs holmes_cli.py directly (CLI mode) — override
# to run our FastAPI wrapper instead; app.py shells out to holmes_cli.py itself.
ENTRYPOINT []
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
