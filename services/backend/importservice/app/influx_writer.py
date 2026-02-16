from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from .config import get_settings
import logging

logger = logging.getLogger(__name__)

class InfluxDBWriter:
    def __init__(self):
        settings = get_settings()
        self.client = InfluxDBClient(
            url=settings.influxdb_url,
            token=settings.influxdb_token,
            org=settings.influxdb_org
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.bucket = settings.influxdb_bucket
        self.org = settings.influxdb_org

    def write_measurements(self, messages: list) -> int:
        """Write flattened measurement messages to InfluxDB"""
        points = []
        
        for msg in messages:
            category = msg.get("category")
            
            # Create a point based on the category
            point = Point(msg["type"])
            
            # Add tags
            point.tag("category", category)
            point.tag("deviceId", msg["deviceId"])
            point.tag("platform", msg["platform"])
            point.tag("sourceName", msg["sourceName"])
            point.tag("unit", msg["unit"])
            
            # Add fields
            point.field("value", float(msg["value"]))
            
            # Set timestamp based on category
            if category == "instantaneous":
                point.time(msg["timestamp"])
            elif category == "cumulative":
                point.time(msg["periodEnd"])
                point.field("durationSeconds", msg["durationSeconds"])
                point.tag("periodStart", msg["periodStart"])
            elif category == "duration":
                point.time(msg["endTime"])
                point.field("durationMinutes", msg["durationMinutes"])
                point.tag("startTime", msg["startTime"])
            
            points.append(point)
        
        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=points)
            logger.info(f"Successfully wrote {len(points)} points to InfluxDB")
            return len(points)
        except Exception as e:
            logger.error(f"Failed to write to InfluxDB: {e}")
            raise

    def close(self):
        """Close the InfluxDB client"""
        self.write_api.close()
        self.client.close()


_influx_writer = None

def get_influx_writer() -> InfluxDBWriter:
    """Dependency for getting InfluxDB writer instance"""
    global _influx_writer
    if _influx_writer is None:
        _influx_writer = InfluxDBWriter()
    return _influx_writer
