FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN mkdir -p config

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libgpiod2 \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY config/config.yml ./config/config.yml

ENTRYPOINT ["python3", "src/climate_agent.py"]
CMD ["--mode", "local"]
