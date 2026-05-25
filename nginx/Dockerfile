FROM nginx:1.27-alpine

RUN apk add --no-cache curl

# Copy files from the correct subdirectories (since build context is project root)
COPY userscript/mentorship.user.js /srv/userscript/mentorship.user.js
COPY nginx/nginx.conf /etc/nginx/nginx.conf

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1