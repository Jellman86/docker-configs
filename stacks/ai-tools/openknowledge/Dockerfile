# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
# No official OpenKnowledge image is published; build the upstream recipe
# from https://openknowledge.ai/docs/remote-control/methods/docker with pins.
FROM node:24-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5

ARG OPENKNOWLEDGE_VERSION=0.86.22

LABEL org.opencontainers.image.title="OpenKnowledge for AI Tools" \
      org.opencontainers.image.description="Pinned @inkeep/open-knowledge server; project data lives on the /data bind mount" \
      org.opencontainers.image.source="https://github.com/inkeep/open-knowledge" \
      org.opencontainers.image.version="0.86.22"

# git is a hard boot requirement: the server runs a git preflight at boot.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@inkeep/open-knowledge@${OPENKNOWLEDGE_VERSION}" \
 && npm list -g @inkeep/open-knowledge

# OK_ALLOW_EXTERNAL is deliberately NOT baked in; Compose supplies it together
# with OK_EXTERNAL_URL, and a run without that pair refuses to boot.
ENV PORT=8080 \
    OK_BIND=0.0.0.0

WORKDIR /data
EXPOSE 8080

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER node
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
