FROM alpine:3.20

# dl-cdn.alpinelinux.org's Fastly-fronted HTTPS endpoint is unreachable from
# some networks (TLS ClientHello gets reset) — repoint at a mirror that's
# confirmed reachable instead of the default.
RUN sed -i 's|https://dl-cdn.alpinelinux.org|https://repo.huaweicloud.com|' /etc/apk/repositories && \
    apk add --no-cache ffmpeg netcat-openbsd ttf-dejavu

COPY media/ /media/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
