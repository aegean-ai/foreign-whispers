FROM python:3.11-slim

RUN apt-get update && \
    apt-get install --no-install-recommends -y openssh-client ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY torch_bridge/requirements.txt /app/torch_bridge/requirements.txt
RUN pip install --no-cache-dir -r /app/torch_bridge/requirements.txt

COPY torch_bridge /app/torch_bridge
ENV PYTHONPATH=/app

EXPOSE 8787
CMD ["uvicorn", "torch_bridge.app:app", "--host", "0.0.0.0", "--port", "8787"]
