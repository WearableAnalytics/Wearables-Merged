package org.example.fhir;

import com.google.gson.*;
import org.example.ConfigLoader;
import org.example.dependencies.DependencyGraph;
import org.example.fhir.model.MappingYaml;
import org.example.lineprotocol.LineProtocolParser;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MeasurementContractTest {
    private final MappingYaml config = ConfigLoader.loadConfig("config/mapping-2026-01-28.yaml", MappingYaml.class);
    private final Mapper mapper = new Mapper(config, 100);

    private JsonObject input(String category, String type, double value, String unit) {
        JsonObject root = JsonParser.parseString("""
            {"deviceInfo":{"deviceId":"participant-1","platform":"ios"},"measurements":
             {"instantaneous":[],"cumulative":[],"duration":[]}}
            """).getAsJsonObject();
        JsonObject reading = new JsonObject();
        reading.addProperty("type", type);
        reading.addProperty("value", value);
        reading.addProperty("unit", unit);
        reading.addProperty("timestamp", "2026-11-12T10:00:00.123456+01:00");
        reading.addProperty("periodStart", "2026-11-12T10:00:00.123456+01:00");
        reading.addProperty("periodEnd", "2026-11-12T11:00:00.123456+01:00");
        reading.addProperty("startTime", "2026-11-12T10:00:00.123456+01:00");
        reading.addProperty("endTime", "2026-11-12T11:00:00.123456+01:00");
        root.getAsJsonObject("measurements").getAsJsonArray(category).add(reading);
        return root;
    }

    @Test void everyDeclaredMetricMapsWithItsCanonicalUnit() {
        for (var path : config.getMeasurement().getPaths()) {
            String category = path.getPath().substring("measurements.".length());
            var codes = path.getMappings().stream().filter(m -> m.getFieldName().equals("codeCodingCodeZero"))
                    .findFirst().orElseThrow();
            for (var entry : codes.getMap()) {
                String unit = NumericMeasurementNormalizer.mapped(path, "valueUnit", entry.getValue());
                var result = mapper.mapFhir(input(category, entry.getKey().toUpperCase().replace('-', '_'), 1, unit).toString());
                assertEquals(unit, result.getValue1().getAsJsonObject("valueQuantity").get("unit").getAsString());
            }
        }
    }

    @Test void distinguishesLightDeepAndHrvMethods() {
        for (String metric : List.of("SLEEP_LIGHT", "SLEEP_ASLEEP_CORE")) {
            var fhir = mapper.mapFhir(input("duration", metric, 1.5, "MINUTE").toString()).getValue1();
            assertEquals("93830-8", fhir.getAsJsonObject("code").getAsJsonArray("coding")
                    .get(0).getAsJsonObject().get("code").getAsString());
        }
        var rmssd = mapper.mapFhir(input("instantaneous", "HEART_RATE_VARIABILITY_RMSSD", 40, "MILLISECOND").toString()).getValue1();
        assertEquals("hrv-rmssd", rmssd.getAsJsonObject("code").getAsJsonArray("coding")
                .get(0).getAsJsonObject().get("code").getAsString());
        var sdnn = mapper.mapFhir(input("instantaneous", "HEART_RATE_VARIABILITY_SDNN", 40, "MILLISECOND").toString()).getValue1();
        assertEquals("80404-7", sdnn.getAsJsonObject("code").getAsJsonArray("coding")
                .get(0).getAsJsonObject().get("code").getAsString());
    }

    @Test void convertsCompatibleUnitsAndRejectsIncompatibleInput() {
        var distance = mapper.mapFhir(input("cumulative", "DISTANCE_WALKING_RUNNING", 1.5, "KILOMETER").toString()).getValue1();
        assertEquals(1500, distance.getAsJsonObject("valueQuantity").get("value").getAsDouble());
        assertEquals("m", distance.getAsJsonObject("valueQuantity").get("code").getAsString());
        assertThrows(IllegalArgumentException.class,
                () -> mapper.mapFhir(input("instantaneous", "HEART_RATE", 72, "KILOGRAM").toString()));
        assertThrows(IllegalArgumentException.class,
                () -> mapper.mapFhir(input("cumulative", "STEPS", -1, "COUNT").toString()));
    }

    @Test void preservesAndroidRateAndAppleEnergy() {
        JsonObject android = input("cumulative", "BASAL_ENERGY_BURNED", 1800, "KILOCALORIE");
        android.getAsJsonObject("deviceInfo").addProperty("platform", "android");
        var rate = mapper.mapFhir(android.toString());
        assertEquals("measurements.instantaneous", rate.getValue0());
        assertEquals("kcal/d", rate.getValue1().getAsJsonObject("valueQuantity").get("unit").getAsString());
        var energy = mapper.mapFhir(input("cumulative", "BASAL_ENERGY_BURNED", 75, "KILOCALORIE").toString());
        assertEquals("measurements.cumulative", energy.getValue0());
        assertEquals("kcal", energy.getValue1().getAsJsonObject("valueQuantity").get("unit").getAsString());
    }

    @Test void preservesFractionalDurationAndIntervalsThroughStorage() throws Exception {
        var mapped = mapper.mapFhir(input("duration", "SLEEP_LIGHT", 90.25, "SECOND").toString());
        assertEquals(90.25 / 60, mapped.getValue1().getAsJsonObject("valueQuantity").get("value").getAsDouble(), 1e-12);
        assertEquals("2026-11-12T10:00:00.123456Z", mapped.getValue1().getAsJsonObject("effectivePeriod").get("end").getAsString());
        DependencyGraph graph = new DependencyGraph(config);
        graph.createGraphBase();
        graph.enrichGraphWithFhir();
        String line = new LineProtocolParser(config).parse(mapped.getValue0(), mapped.getValue1(), graph.build().get(mapped.getValue0()));
        assertTrue(line.contains("period_end=\"2026-11-12T10:00:00.123456Z\""), line);
        assertTrue(line.contains("input_unit=\"SECOND\""), line);
        assertTrue(line.contains("version=2.1.0"), line);
        Files.createDirectories(Path.of("target/contract"));
        Files.writeString(Path.of("target/contract/sleep-light.lp"), line);
    }

    @Test void distinguishesWorkoutActiveAndElapsedTime() {
        var active = mapper.mapFhir(input("duration", "WORKOUT_ACTIVE_TIME", 20, "MINUTE").toString()).getValue1();
        var elapsed = mapper.mapFhir(input("duration", "WORKOUT_ELAPSED_TIME", 60, "MINUTE").toString()).getValue1();
        assertEquals(20, active.getAsJsonObject("valueQuantity").get("value").getAsDouble());
        assertNotEquals(active.getAsJsonObject("code"), elapsed.getAsJsonObject("code"));
        assertThrows(IllegalArgumentException.class,
            () -> mapper.mapFhir(input("duration", "WORKOUT_ACTIVE_TIME", 61, "MINUTE").toString()));
    }

    @Test void retainsNumericLookingNativeIdsAndSeparatesPhysicalSources() throws Exception {
        JsonObject root = input("instantaneous", "HEART_RATE", 72, "BEATS_PER_MINUTE");
        root.addProperty("sourcePlatform", "apple-health");
        root.addProperty("sourceId", "com.example.health");
        root.addProperty("sourceName", "Watch App");
        JsonObject reading = root.getAsJsonObject("measurements").getAsJsonArray("instantaneous").get(0).getAsJsonObject();
        reading.addProperty("sourceRecordId", "00123");
        reading.addProperty("sourceDeviceId", "watch-1");
        var first = mapper.mapFhir(root.toString());
        reading.addProperty("sourceDeviceId", "watch-2");
        var second = mapper.mapFhir(root.toString());
        DependencyGraph graph = new DependencyGraph(config);
        graph.createGraphBase(); graph.enrichGraphWithFhir();
        var basis = graph.build().get(first.getValue0());
        LineProtocolParser parser = new LineProtocolParser(config);
        String line = parser.parse(first.getValue0(), first.getValue1(), basis);
        String other = parser.parse(second.getValue0(), second.getValue1(), basis);
        assertTrue(line.contains("source_record_id=\"00123\""), line);
        var sourceTag = java.util.regex.Pattern.compile("(?:^|,)source-key=([a-f0-9]{64})");
        var one = sourceTag.matcher(line);
        var two = sourceTag.matcher(other);
        assertTrue(one.find(), line);
        assertTrue(two.find(), other);
        assertNotEquals(one.group(1), two.group(1));
        Files.writeString(Path.of("target/contract/source.lp"), line);
    }
}
