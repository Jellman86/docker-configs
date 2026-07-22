FROM alpine:3.22@sha256:7c8cb692ae09657cbc4a3f3cbd0e8d5a2690ba38386aaaf252dbb060bf5eb2e6 AS downloader

ARG HIMALAYA_VERSION=1.2.0
ARG HIMALAYA_SHA256=e04e6382e3e664ef34b01afa1a2216113194a2975d2859727647b22d9b36d4e4

RUN apk add --no-cache ca-certificates curl tar \
    && curl --fail --location --silent --show-error --retry 3 \
        --output /tmp/himalaya.tgz \
        "https://github.com/pimalaya/himalaya/releases/download/v${HIMALAYA_VERSION}/himalaya.x86_64-linux.tgz" \
    && echo "${HIMALAYA_SHA256}  /tmp/himalaya.tgz" | sha256sum -c - \
    && tar -xzf /tmp/himalaya.tgz -C /usr/local/bin himalaya \
    && chmod 0755 /usr/local/bin/himalaya

FROM alpine:3.22@sha256:7c8cb692ae09657cbc4a3f3cbd0e8d5a2690ba38386aaaf252dbb060bf5eb2e6

RUN apk add --no-cache ca-certificates

COPY --from=downloader /usr/local/bin/himalaya /usr/local/bin/himalaya
COPY config.toml /etc/himalaya/config.toml

ENV HIMALAYA_CONFIG=/etc/himalaya/config.toml \
    HOME=/tmp

CMD ["sh", "-ec", "test -n \"$ICLOUD_EMAIL\"; test -n \"$ICLOUD_IMAP_LOGIN\"; test -n \"$ICLOUD_APP_PASSWORD\"; exec tail -f /dev/null"]
