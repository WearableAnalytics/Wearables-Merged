from app.kafka_publisher import CloudKafkaPublisher


def test_publisher_preserves_method_identity_and_offsets():
    original = {
        "measurements": {"instantaneous": [
            {"type": "HEART_RATE_VARIABILITY_RMSSD", "timestamp": "2026-11-12T10:00:00.123456+01:00"},
        ], "duration": [{"type": "SLEEP_LIGHT", "startTime": "2026-11-12T09:00:00Z"}]},
    }
    assert CloudKafkaPublisher._normalize_for_fhir_mapper(original) == original
