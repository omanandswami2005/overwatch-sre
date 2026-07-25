FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY app.py .
COPY toolsets/ toolsets/
COPY toolsets.yaml .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
