FROM node:20.20.2-alpine3.23@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS build
WORKDIR /app
ARG SOURCE_DATE_EPOCH=0
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
RUN npm run build \
    && install -d /runtime-root/etc/nginx/templates /runtime-root/etc/nginx /runtime-root/usr/local/bin /runtime-root/usr/share/nginx \
    && cp nginx/default.conf.template /runtime-root/etc/nginx/templates/default.conf.template \
    && cp nginx/nginx-readonly.conf /runtime-root/etc/nginx/nginx-readonly.conf \
    && cp nginx/readonly-entrypoint.sh /runtime-root/usr/local/bin/video-nginx-entrypoint \
    && cp -a dist /runtime-root/usr/share/nginx/html \
    && find /runtime-root -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +

FROM nginxinc/nginx-unprivileged:1.27.5-alpine@sha256:65e3e85dbaed8ba248841d9d58a899b6197106c23cb0ff1a132b7bfe0547e4c0
COPY --from=build /runtime-root /
ENV BACKEND_ORIGIN=http://video:8010 \
    ALLOWED_FRAME_ANCESTORS=""
ENTRYPOINT ["/bin/sh", "/usr/local/bin/video-nginx-entrypoint"]
EXPOSE 80
