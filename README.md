# Trachs - Google Find My Device to Traccar Bridge

A service that polls Google Find My Device for location data and forwards it to a [Traccar](https://www.traccar.org/) server using the OsmAnd protocol.

## Features

- Periodically polls all devices registered in your Google Find My Device account
- Sends location updates to Traccar via the OsmAnd protocol
- Configurable polling interval
- Flexible device name to Traccar ID mapping
- Docker support for easy deployment
- Dry-run mode for testing

## Quick Start

### Deploy from Pre-built Image (Recommended for servers)

1. **On your server, create a directory and download the compose file:**

   ```bash
   mkdir trachs && cd trachs
   curl -O https://raw.githubusercontent.com/derenrich/trachs/main/docker-compose.prod.yml
   curl -O https://raw.githubusercontent.com/derenrich/trachs/main/.env.example
   mv .env.example .env
   ```

2. **Copy your `secrets.json` to the server:**

   ```bash
   scp /path/to/secrets.json yourserver:~/trachs/secrets.json
   ```

3. **Edit `.env` with your configuration:**

   ```bash
   TRACCAR_URL=http://your-traccar-server:5055
   DEVICE_MAPPING={"Pixel 8 Pro": "mypixel", "Tag": "mytag"}
   ```

4. **Start the service:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

### Using Docker Compose (Local Development)

1. **Copy the example environment file:**

   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your configuration:**

   ```bash
   # Required: URL of your Traccar server
   TRACCAR_URL=http://your-traccar-server:5055

   # Optional: Map device names to Traccar device IDs
   DEVICE_MAPPING={"Pixel 8 Pro": "mypixel", "Tag": "mytag"}
   ```

3. **Ensure your `secrets.json` is in place:**
   The secrets file should be at `./src/Auth/secrets.json` (or update `SECRETS_FILE` in `.env`)

4. **Start the service:**
   ```bash
   docker compose up -d
   ```

### Building the Docker Image

```bash
# Build locally
docker build -t trachs:latest .

# Or use docker compose
docker compose build
```

## Configuration

All configuration is done via environment variables:

| Variable                   | Default                 | Description                                 |
| -------------------------- | ----------------------- | ------------------------------------------- |
| `TRACCAR_URL`              | `http://localhost:5055` | URL of Traccar's OsmAnd protocol endpoint   |
| `SECRETS_PATH`             | `/app/secrets.json`     | Path to secrets.json inside container       |
| `POLL_INTERVAL_SECONDS`    | `300`                   | How often to poll for locations (5 minutes) |
| `REQUEST_TIMEOUT_SECONDS`  | `60`                    | HTTP request timeout                        |
| `DEVICE_MAPPING`           | `{}`                    | JSON mapping of device names to Traccar IDs |
| `AUTO_GENERATE_DEVICE_IDS` | `true`                  | Auto-generate Traccar IDs from device names |
| `TRACCAR_ENABLED`          | `true`                  | Set to `false` for dry-run mode             |
| `LOG_LEVEL`                | `INFO`                  | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `PUID` and `PGID`          | `1000`                  | User and group IDs to run as                |

### Device Mapping

You can explicitly map Google device names to Traccar device IDs:

```bash
DEVICE_MAPPING={"My Phone": "phone001", "Pebblebee Tag": "tag001"}
```

Or enable auto-generation (default) which creates IDs by lowercasing the device name and removing non-alphanumeric characters:

- "Pixel 8 Pro" → `pixel8pro`
- "My Tag (Blue)" → `mytagblue`

### Setting Up Traccar

1. In Traccar, create a device for each tracker you want to monitor
2. Set the device's "Identifier" to match either:
   - The value in your `DEVICE_MAPPING`, or
   - The auto-generated ID from the device name
3. Ensure port 5055 (OsmAnd protocol) is accessible

## Generating secrets.json

The `secrets.json` file contains authentication tokens for Google Find My Device. See the original [GoogleFindMyTools](https://github.com/leonboe1/GoogleFindMyTools) documentation for instructions on generating this file.

## Running Without Docker

```bash
# Install dependencies
uv sync

# Set environment variables
export TRACCAR_URL=http://your-traccar-server:5055
export SECRETS_PATH=./src/Auth/secrets.json

# Run
uv run python ./src/main.py
```

## Docker Image

The Docker image is automatically built and published to GitHub Container Registry on every push to main.

**Pull the latest image:**

```bash
docker pull ghcr.io/derenrich/trachs:latest
```

## License

This is distributed under GPL-3.0 license

Uses work from https://github.com/leonboe1/GoogleFindMyTools which is also under GPL-3.0 license
