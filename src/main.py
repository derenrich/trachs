#!/usr/bin/env python3
"""
Trachs Service - Google Find My Device to Traccar Bridge

This service periodically polls Google Find My Device for location data
and forwards it to a Traccar server using the OsmAnd protocol.
"""

import asyncio
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import httpx

from NovaApi.ListDevices.nbe_list_devices import request_device_list
from NovaApi.ExecuteAction.LocateTracker.location_request import get_location_data_for_device
from ProtoDecoders.decoder import parse_device_list_protobuf, get_canonic_ids
from SpotApi.UploadPrecomputedPublicKeyIds.upload_precomputed_public_key_ids import refresh_custom_trackers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class Config:
    """Configuration loaded from environment variables."""
    
    def __init__(self):
        # Required
        self.traccar_url = os.environ.get('TRACCAR_URL', 'http://localhost:5055')
        self.secrets_path = os.environ.get('SECRETS_PATH', '/app/secrets.json')
        
        # Optional with defaults
        self.poll_interval_seconds = int(os.environ.get('POLL_INTERVAL_SECONDS', '900'))
        self.request_timeout_seconds = int(os.environ.get('REQUEST_TIMEOUT_SECONDS', '60'))
        
        # Device name to Traccar ID mapping (JSON string)
        # Format: {"Device Name": "traccar_device_id", ...}
        device_mapping_str = os.environ.get('DEVICE_MAPPING', '{}')
        try:
            self.device_mapping: dict[str, str] = json.loads(device_mapping_str)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid DEVICE_MAPPING JSON: {e}")
            self.device_mapping = {}
        
        # If no explicit mapping, use auto-generated IDs based on device name
        self.auto_generate_device_ids = os.environ.get('AUTO_GENERATE_DEVICE_IDS', 'false').lower() == 'true'
        
        # Enable/disable sending to Traccar (useful for testing)
        self.traccar_enabled = os.environ.get('TRACCAR_ENABLED', 'true').lower() == 'true'
        
        # Log level
        log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))
    
    def get_traccar_device_id(self, device_name: str, canonic_id: str) -> Optional[str]:
        """Get the Traccar device ID for a given device name."""
        # First check explicit mapping
        if device_name in self.device_mapping:
            return self.device_mapping[device_name]
        
        # Check if canonic_id is mapped
        if canonic_id in self.device_mapping:
            return self.device_mapping[canonic_id]
        
        # Auto-generate if enabled
        if self.auto_generate_device_ids:
            # Create a stable ID from device name (alphanumeric only, lowercase)
            return ''.join(c.lower() for c in device_name if c.isalnum()) or canonic_id[:16]
        
        return None
    
    def validate(self) -> bool:
        """Validate the configuration."""
        if not self.traccar_url:
            logger.error("TRACCAR_URL is required")
            return False
        
        # Check if secrets file exists (use the same logic as token_cache)
        secrets_file = self.secrets_path
        if not os.path.exists(secrets_file):
            # Try the default location relative to Auth module
            from Auth import token_cache
            default_secrets = token_cache._get_secrets_file()
            if not os.path.exists(default_secrets):
                logger.error(f"Secrets file not found. Checked: {secrets_file} and {default_secrets}")
                return False
            else:
                logger.info(f"Using secrets file at: {default_secrets}")
        else:
            logger.info(f"Using secrets file at: {secrets_file}")
        
        return True


async def send_to_traccar(
    client: httpx.AsyncClient,
    config: Config,
    device_id: str,
    latitude: float,
    longitude: float,
    altitude: float,
    timestamp: int,
    is_own_report: bool,
    accuracy: Optional[float] = None
) -> bool:
    """Send location data to Traccar using the OsmAnd protocol."""
    
    if not config.traccar_enabled:
        logger.info(f"[DRY RUN] Would send to Traccar: device={device_id}, lat={latitude}, lon={longitude}")
        return True
    
    # Build the OsmAnd protocol URL

    extras = dict()
    extras['is_own_report'] = str(is_own_report)

    params = {
        'id': device_id,
        'lat': latitude,
        'lon': longitude,
        'timestamp': timestamp,  # Unix timestamp in seconds
        'altitude': altitude,
        'extras': json.dumps(extras)
    }
    
    if accuracy is not None and accuracy > 0:
        params['accuracy'] = accuracy
    
    try:
        response = await client.get(config.traccar_url, params=params, timeout=config.request_timeout_seconds)
        
        if response.status_code == 200:
            logger.info(f"Successfully sent location for device {device_id} to Traccar")
            return True
        else:
            logger.warning(f"Traccar returned status {response.status_code}: {response.text}")
            return False
            
    except httpx.RequestError as e:
        logger.error(f"Failed to send to Traccar: {e}")
        return False


def poll_device_locations(config: Config) -> list[dict]:
    """Poll Google Find My Device for all device locations."""
    
    locations = []
    
    try:
        logger.info("Requesting device list from Google Find My Device...")
        result_hex = request_device_list()
        device_list = parse_device_list_protobuf(result_hex)
        
        # Refresh custom tracker EIDs
        refresh_custom_trackers(device_list)
        
        canonic_ids = get_canonic_ids(device_list)
        logger.info(f"Found {len(canonic_ids)} devices")
        
        for device_name, canonic_id in canonic_ids:
            traccar_id = config.get_traccar_device_id(device_name, canonic_id)
            
            if traccar_id is None:
                logger.debug(f"Skipping device '{device_name}' - no Traccar ID mapping")
                continue
            
            try:
                logger.info(f"Requesting location for '{device_name}'...")
                locations_list = get_location_data_for_device(canonic_id, device_name)
                
                if not locations_list:
                    logger.warning(f"No locations returned for '{device_name}'")
                    continue
                
                # Use the most recent location (last in the list)
                loc = locations_list[-1]
                
                # Parse the proto location from decrypted bytes
                from ProtoDecoders import DeviceUpdate_pb2
                proto_loc = DeviceUpdate_pb2.Location()
                
                # Skip semantic locations (they don't have coordinates)
                from ProtoDecoders import Common_pb2
                if loc.status == Common_pb2.Status.SEMANTIC:
                    logger.info(f"Skipping semantic location for '{device_name}': {loc.name}")
                    continue
                
                proto_loc.ParseFromString(loc.decrypted_location)
                
                # Extract location data
                location_data = {
                    'device_name': device_name,
                    'canonic_id': canonic_id,
                    'traccar_id': traccar_id,
                    'latitude': proto_loc.latitude / 1e7,  # Convert from microdegrees
                    'longitude': proto_loc.longitude / 1e7,
                    'altitude': proto_loc.altitude,
                    'timestamp': loc.time,
                    'accuracy': loc.accuracy,
                    'status': loc.status,
                    'is_own_report': loc.is_own_report,
                }
                
                locations.append(location_data)
                logger.info(
                    f"Got location for '{device_name}': "
                    f"({location_data['latitude']}, {location_data['longitude']})"
                )
                
            except Exception as e:
                logger.error(f"Failed to get location for '{device_name}': {e}")
                continue
    
    except Exception as e:
        logger.error(f"Failed to poll device locations: {e}")
    
    return locations


async def run_polling_loop(config: Config):
    """Main polling loop that runs continuously."""
    
    logger.info("Starting Trachs polling service...")
    logger.info(f"Traccar URL: {config.traccar_url}")
    logger.info(f"Poll interval: {config.poll_interval_seconds} seconds")
    logger.info(f"Device mapping: {config.device_mapping}")
    logger.info(f"Auto-generate IDs: {config.auto_generate_device_ids}")
    logger.info(f"Traccar enabled: {config.traccar_enabled}")
    
    # Use a thread pool to run the synchronous Google API calls
    # This avoids "Cannot run the event loop while another loop is running" errors
    executor = ThreadPoolExecutor(max_workers=1)
    
    async with httpx.AsyncClient(headers={"User-Agent": "Trachs"}) as client:
        last_timestamps = dict()
        while True:
            try:
                logger.info("Starting polling cycle...")
                start_time = time.time()
                
                # Poll for locations in a thread pool to avoid event loop conflicts
                # The Google API code uses its own asyncio loops internally
                loop = asyncio.get_event_loop()
                locations = await loop.run_in_executor(executor, poll_device_locations, config)
                
                # Send each location to Traccar
                for loc in locations:
                    device_id = loc['traccar_id']
                    ts = loc['timestamp']

                    if device_id in last_timestamps and ts <= last_timestamps[device_id]:
                        logger.info(f"Skipping older location for device {device_id}")
                        continue
                    last_timestamps[device_id] = ts
                    await send_to_traccar(
                        client=client,
                        config=config,
                        device_id=device_id,
                        latitude=loc['latitude'],
                        longitude=loc['longitude'],
                        altitude=loc['altitude'],
                        timestamp=ts,
                        accuracy=loc['accuracy'],
                        is_own_report=loc['is_own_report']
                    )
                
                elapsed = time.time() - start_time
                logger.info(f"Polling cycle complete. Processed {len(locations)} locations in {elapsed:.1f}s")
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
            
            # Wait for next poll
            logger.info(f"Sleeping for {config.poll_interval_seconds} seconds...")
            await asyncio.sleep(config.poll_interval_seconds)


def main():
    """Main entry point."""
    
    # Load configuration
    config = Config()
    
    # Validate configuration
    if not config.validate():
        logger.error("Configuration validation failed")
        sys.exit(1)
    
    # Run the polling loop
    try:
        asyncio.run(run_polling_loop(config))
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == '__main__':
    main()
