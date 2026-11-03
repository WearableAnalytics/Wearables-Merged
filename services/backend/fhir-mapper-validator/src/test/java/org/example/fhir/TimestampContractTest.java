package org.example.fhir;

import com.google.gson.JsonPrimitive;
import org.example.fhir.model.FieldConfig;
import org.example.fhir.model.ValueTransformation;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class TimestampContractTest {
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
