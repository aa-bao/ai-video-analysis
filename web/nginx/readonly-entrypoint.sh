#!/bin/sh
set -eu

# Standalone deployment: no platform injection (独立化改造已移除平台组件间路由注入)。
# compose 会注入 BACKEND_ORIGIN；这里保留同义默认值，使容器脱离 compose 也能起。
BACKEND_ORIGIN="${BACKEND_ORIGIN:-http://video:8010}"
export BACKEND_ORIGIN

envsubst '${BACKEND_ORIGIN} ${ALLOWED_FRAME_ANCESTORS}' \
  < /etc/nginx/templates/default.conf.template \
  > /tmp/rag-default.conf

exec nginx -c /etc/nginx/nginx-readonly.conf -g 'daemon off;'
