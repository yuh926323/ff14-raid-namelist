FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY ff14_raid_namelist ./ff14_raid_namelist

RUN pip install --no-cache-dir ".[bot]"

CMD ["python", "-m", "ff14_raid_namelist.bot"]
