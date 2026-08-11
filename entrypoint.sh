#!/bin/bash
set -e
if [ "$TRYON_DEV" = "1" ]; then
    echo "Starting in DEV mode"
    exec python3 server.py
else
    echo "Starting with gunicorn"
    exec gunicorn -w 1 -b 0.0.0.0:7860 --timeout 600 "server:app"
fi
