#!/bin/sh
set -eu

# Railway mounts persistent volumes after image build, so image-time chown is
# insufficient. Perform the minimal privileged hand-off, then run the API as
# the dedicated non-root user.
if [ -d /data ]; then
  chown -R appuser:appuser /data
fi

exec su -s /bin/sh appuser -c 'exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"'
