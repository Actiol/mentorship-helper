FROM nginx:1.27-alpine

RUN apk add --no-cache curl

COPY nginx.conf /etc/nginx/nginx.conf

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1
