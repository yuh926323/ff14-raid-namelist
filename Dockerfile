FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/works/ff14-raid-namelist
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        less \
        vim \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 python \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash python

COPY pyproject.toml README.md ./
COPY ff14_raid_namelist ./ff14_raid_namelist
COPY docker/start-python.sh /usr/local/bin/start-python

RUN pip install --no-cache-dir ".[bot]"
RUN chmod +x /usr/local/bin/start-python

WORKDIR /works

CMD ["/usr/local/bin/start-python"]
