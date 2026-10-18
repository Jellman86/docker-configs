#!/bin/sh
# First-boot init: scaffold the project exactly once, on an empty volume.
# An initialized or restored volume starts the server.
# stdin is closed so `ok init` takes its non-TTY defaults and can never
# hang on a prompt.
set -eu
if [ ! -d /data/.ok ]
then
  echo "[entrypoint] /data is not initialized. Running ok init --no-mcp --no-skills"
  ok init --no-mcp --no-skills < /dev/null
fi
exec ok start
