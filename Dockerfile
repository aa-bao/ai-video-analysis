FROM python:3.12.14-slim-trixie AS build
WORKDIR /app
ARG SOURCE_DATE_EPOCH=0
ENV UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.7.5 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . ./
RUN find /app -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +

FROM python:3.12.14-slim-trixie
WORKDIR /app

ARG SOURCE_DATE_EPOCH=0
ARG APP_UID=10001
RUN printf 'appuser:x:%s:%s:Application User:/nonexistent:/usr/sbin/nologin\n' "${APP_UID}" "${APP_UID}" >> /etc/passwd \
    && printf 'appuser:x:%s:\n' "${APP_UID}" >> /etc/group \
    && install -d -o appuser -g appuser /app/data \
    && install -d -o appuser -g appuser /app/data/video \
    && install -d -o appuser -g appuser /app/data/video/tasks \
    && install -d -o appuser -g appuser /app/data/video/output \
    && install -d -o appuser -g appuser /app/data/video/uploads \
    && install -d -o appuser -g appuser /app/data/video/library \
    && install -d -o appuser -g appuser /app/data/video/cookies \
    && touch -h -d "@${SOURCE_DATE_EPOCH}" \
        /etc \
        /etc/passwd \
        /etc/group \
        /app

COPY --from=build --chown=10001:10001 /app /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    APP_DATA_ROOT=/app/data \
    APP_SECRET_ROOT=/run/secrets

EXPOSE 8010
CMD ["uvicorn", "src.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
