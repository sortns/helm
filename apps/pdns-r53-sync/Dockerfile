# syntax=docker/dockerfile:1
FROM python:3.12.15-slim-trixie AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-deps -r /tmp/requirements.txt \
 && /opt/venv/bin/pip check

FROM python:3.12.15-slim-trixie
LABEL org.opencontainers.image.source="https://github.com/sortns/helm" \
      org.opencontainers.image.description="Mirror a PowerDNS zone from Poweradmin API v2 to AWS Route53"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=build /opt/venv /opt/venv
COPY pa_sync /app/pa_sync
WORKDIR /app
USER 10001:10001
EXPOSE 9100
ENTRYPOINT ["python", "-m", "pa_sync"]
CMD ["run"]
