package org.example.fhir;

import com.google.gson.JsonPrimitive;
import org.example.dependencies.DependencyGraph;
import org.example.fhir.model.*;
import org.example.fhir.model.ValueTransformation;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class TimestampContractTest {
    @Test
    void dependencyGraphRetainsRawTimestampAsBasisWhenNormalizationLosesOffsetSpelling() {
        ValueTransformation normalization = new ValueTransformation();
        normalization.setType("normalizeTimestamp");
        FieldConfig normalized = new FieldConfig();
        normalized.setName("t");
        normalized.setLineProtocol(new LineProtocol());
        normalized.getLineProtocol().setType("timestamp");
        normalized.setRawSource("measurements.instantaneous.timestamp");
        normalized.setTransform(List.of(normalization));
        FieldConfig original = new FieldConfig();
        original.setName("rawTimestamp");
        original.setLineProtocol(new LineProtocol());
        original.getLineProtocol().setType("timestamp");
        original.setRawSource(normalized.getRawSource());
        original.setTransform(List.of());
        MetadataConfig metadata = new MetadataConfig();
        metadata.setFields(List.of());
        MeasurementPathConfig category = new MeasurementPathConfig();
        category.setPath("measurements.instantaneous");
        FieldConfig metric = new FieldConfig();
        metric.setName("metric");
        metric.setRawSource("measurements.instantaneous.type");
        metric.setLineProtocol(new LineProtocol());
        metric.getLineProtocol().setType("measurement");
        FieldConfig value = new FieldConfig();
        value.setName("value");
        value.setRawSource("measurements.instantaneous.value");
        value.setLineProtocol(new LineProtocol());
        value.getLineProtocol().setType("field");
        category.setFields(List.of(normalized, original, metric, value));
        MeasurementConfig measurement = new MeasurementConfig();
        measurement.setPaths(List.of(category));
        MappingYaml yaml = new MappingYaml();
        yaml.setMetadata(metadata);
        yaml.setMeasurement(measurement);
        DependencyGraph graph = new DependencyGraph(yaml);
        graph.createGraphBase();
        var basis = graph.build().get(category.getPath());
        assertTrue(basis.stream().anyMatch(node -> node.getField().getName().equals("rawTimestamp")));
        assertFalse(basis.stream().anyMatch(node -> node.getField().getName().equals("t")));
    }

    @Test
    void preservesInstantsAndMicrosecondsAcrossOffsetsAndDst() {
        String[][] cases = {
            {"2026-11-03T10:00:00.123456+01:00", "2026-11-03T09:00:00.123456Z"},
            {"2026-07-03T10:00:00+02:00", "2026-07-03T08:00:00Z"},
            {"2026-10-25T02:30:00+02:00", "2026-10-25T00:30:00Z"},
            {"2026-10-25T02:30:00+01:00", "2026-10-25T01:30:00Z"},
            {"2026-03-29T01:59:59+01:00", "2026-03-29T00:59:59Z"},
            {"2026-03-29T03:00:00+02:00", "2026-03-29T01:00:00Z"},
            {"2026-11-03T09:00:00Z", "2026-11-03T09:00:00Z"},
            {"2026-11-03T09:00:00", "2026-11-03T09:00:00Z"},
        };
        for (String[] example : cases) {
            assertEquals(example[1], Transformer.normalizeTimestamp(new JsonPrimitive(example[0])).getAsString());
        }
        assertThrows(RuntimeException.class,
            () -> Transformer.normalizeTimestamp(new JsonPrimitive("not a timestamp")));
    }

    @Test
    void rawAndFhirTransformationDispatchUseTimestampContract() {
        ValueTransformation transformation = new ValueTransformation();
        transformation.setType("normalizeTimestamp");
        FieldConfig field = new FieldConfig();
        field.setName("start");
        field.setType("string");
        field.setTransform(List.of(transformation));
        var value = new JsonPrimitive("2026-11-03T10:00:00.123456+01:00");
        assertEquals("2026-11-03T09:00:00.123456Z",
            RawTransformer.resolveRawTransformation(field, null, value).getAsString());
        assertEquals("2026-11-03T09:00:00.123456Z",
            FhirTransformer.resolveFhirTransformation(field, null, value).getAsString());
    }
}
