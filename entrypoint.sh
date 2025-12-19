#!/bin/bash
set -e

# Default to UID/GID 1000 if not specified
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Only modify user/group if running as root
if [ "$(id -u)" = "0" ]; then
    # Update appuser's UID if different
    if [ "$(id -u appuser)" != "$PUID" ]; then
        usermod -u "$PUID" appuser
    fi
    
    # Update appuser's GID if different
    if [ "$(id -g appuser)" != "$PGID" ]; then
        groupmod -g "$PGID" appuser
    fi
    
    # Fix ownership of app directory
    chown -R appuser:appuser /app
    
    # Run as appuser
    exec gosu appuser "$@"
else
    # Not running as root, just execute the command
    exec "$@"
fi
