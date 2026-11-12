package org.example.fhir;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.example.fhir.model.MappingYaml;
import org.example.fhir.model.MeasurementPathConfig;

import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** Normalizes only the numeric measurements declared by the active mapping. */
final class NumericMeasurementNormalizer {
    static final String CONTRACT = "wearables-numeric/2";

    private NumericMeasurementNormalizer() {}

    static JsonObject normalize(JsonObject original, MappingYaml mapping) {
        if (mapping.getNumericContract() == null) return original;
        if (!CONTRACT.equals(mapping.getNumericContract())) {
            throw new IllegalArgumentException("Unsupported numeric mapping contract");
        }
        JsonObject input = original.deepCopy();
        if (!input.has("participantId") || input.get("participantId").isJsonNull()) {
            input.add("participantId", input.getAsJsonObject("deviceInfo").get("deviceId"));
        }
        JsonObject measurements = input.getAsJsonObject("measurements");
        normalizeLegacyAndroidBmr(input, measurements);
        for (MeasurementPathConfig path : mapping.getMeasurement().getPaths()) {
            String category = path.getPath().substring("measurements.".length());
            JsonArray readings = measurements.getAsJsonArray(category);
            if (readings == null) continue;
            for (var element : readings) {
                JsonObject reading = element.getAsJsonObject();
                normalizeReading(reading, path, category);
                preserveSource(input, reading);
            }
        }
        return input;
    }

    private static void preserveSource(JsonObject input, JsonObject reading) {
        String platform = text(input, "sourcePlatform");
        String writer = text(input, "sourceId");
        String measuringDevice = text(reading, "sourceDeviceId");
        putText(reading, "sourcePlatform", platform);
        putText(reading, "sourceId", writer);
        putText(reading, "sourceName", text(input, "sourceName"));
        putText(reading, "collectorId", text(input.getAsJsonObject("deviceInfo"), "deviceId"));
        putText(reading, "sourceDeviceId", measuringDevice);
        putText(reading, "sourceRecordId", text(reading, "sourceRecordId"));
        // Missing native writer IDs remain an explicit legacy source. Never use
        // the collector installation as a substitute for a writing application.
        com.google.gson.JsonArray identity = new com.google.gson.JsonArray();
        identity.add(platform);
        identity.add(writer);
        identity.add(measuringDevice);
        try {
            String key = writer.isEmpty() ? "legacy" : HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(identity.toString().getBytes(StandardCharsets.UTF_8)));
            reading.addProperty("sourceKey", key);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static void putText(JsonObject object, String name, String value) {
        if (value.isEmpty()) object.remove(name);
        else object.addProperty(name, value);
    }

    private static String text(JsonObject object, String key) {
        if (object == null || !object.has(key) || object.get(key).isJsonNull()) return "";
        String value = object.get(key).getAsString();
        if (value.length() > 512 || value.chars().anyMatch(c -> c < 32)) {
            throw new IllegalArgumentException("Invalid source metadata");
        }
        return value;
    }

    private static void normalizeLegacyAndroidBmr(JsonObject input, JsonObject measurements) {
        String platform = input.has("deviceInfo")
                ? input.getAsJsonObject("deviceInfo").get("platform").getAsString().toLowerCase(Locale.ROOT) : "";
        if (!platform.contains("android")) return;
        JsonArray cumulative = measurements.getAsJsonArray("cumulative");
        if (cumulative == null) return;
        if (!measurements.has("instantaneous")) measurements.add("instantaneous", new JsonArray());
        for (int i = cumulative.size() - 1; i >= 0; i--) {
            JsonObject reading = cumulative.get(i).getAsJsonObject();
            if (!"BASAL_ENERGY_BURNED".equalsIgnoreCase(reading.get("type").getAsString())) continue;
            reading.addProperty("type", "BASAL_METABOLIC_RATE");
            reading.add("timestamp", reading.get("periodStart"));
            reading.add("inputUnit", reading.get("unit"));
            reading.addProperty("unit", "KILOCALORIE_PER_DAY");
            measurements.getAsJsonArray("instantaneous").add(reading);
            cumulative.remove(i);
        }
    }

    private static void normalizeReading(JsonObject reading, MeasurementPathConfig path, String category) {
        String metric = reading.get("type").getAsString().toLowerCase(Locale.ROOT).replace('_', '-');
        if (metric.equals("sleep-asleep-core")) {
            metric = "sleep-light";
            reading.addProperty("type", "SLEEP_LIGHT");
        }
        String code = mapped(path, "codeCodingCodeZero", metric);
        String canonicalUnit = mapped(path, "valueUnit", code);
        String inputUnit = reading.get("unit").getAsString();
        double inputValue = reading.get("value").getAsDouble();
        if (!Double.isFinite(inputValue) || inputValue < 0) {
            throw new IllegalArgumentException("Measurement value must be finite and nonnegative");
        }
        double value = convert(inputValue, inputUnit, canonicalUnit);
        if (!Double.isFinite(value)) throw new IllegalArgumentException("Converted value must be finite");
        reading.addProperty("inputValue", inputValue);
        if (!reading.has("inputUnit")) reading.addProperty("inputUnit", inputUnit);
        reading.addProperty("value", value);
        reading.addProperty("unit", canonicalUnit);
        String startKey = category.equals("instantaneous") ? "timestamp"
                : category.equals("cumulative") ? "periodStart" : "startTime";
        String originalStart = reading.get(startKey).getAsString();
        reading.addProperty("timestampPolicy", hasOffset(originalStart) ? "explicit-offset" : "legacy-assumed-utc");
        String start = Transformer.normalizeTimestamp(reading.get(startKey)).getAsString();
        reading.addProperty(startKey, start);
        if (!category.equals("instantaneous")) {
            String endKey = category.equals("cumulative") ? "periodEnd" : "endTime";
            String end = Transformer.normalizeTimestamp(reading.get(endKey)).getAsString();
            reading.addProperty(endKey, end);
            double elapsedSeconds = Duration.between(Instant.parse(start), Instant.parse(end)).toNanos() / 1e9;
            if (elapsedSeconds < 0) throw new IllegalArgumentException("Measurement interval is reversed");
            if (category.equals("duration") && value > elapsedSeconds / 60.0 + 1e-6) {
                throw new IllegalArgumentException("Active duration exceeds elapsed interval");
            }
        }
    }

    static String mapped(MeasurementPathConfig path, String name, String key) {
        return path.getMappings().stream().filter(m -> name.equals(m.getFieldName()))
                .flatMap(m -> m.getMap().stream()).filter(entry -> key.equals(entry.getKey()))
                .map(entry -> entry.getValue()).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unsupported " + name + " value: " + key));
    }

    private static boolean hasOffset(String timestamp) {
        return timestamp.endsWith("Z") || timestamp.matches(".*[+-]\\d{2}:\\d{2}$");
    }

    static double convert(double value, String input, String target) {
        String unit = input.toUpperCase(Locale.ROOT);
        if (input.equals(target)) return value;
        return switch (target) {
            case "/min" -> switch (unit) {
                case "BEATS_PER_MINUTE", "COUNT_PER_MINUTE", "BREATHS_PER_MINUTE", "BPM", "BREATHS/MIN" -> value;
                default -> incompatible(input, target);
            };
            case "1" -> switch (unit) {
                case "COUNT", "ONE", "{STEPS}", "{COUNT}" -> value;
                default -> incompatible(input, target);
            };
            case "ms" -> switch (unit) {
                case "MILLISECOND" -> value;
                case "SECOND", "S" -> value * 1000;
                default -> incompatible(input, target);
            };
            case "min" -> switch (unit) {
                case "MINUTE" -> value;
                case "SECOND", "S" -> value / 60;
                case "HOUR", "H" -> value * 60;
                default -> incompatible(input, target);
            };
            case "m" -> switch (unit) {
                case "METER" -> value;
                case "KILOMETER", "KM" -> value * 1000;
                default -> incompatible(input, target);
            };
            case "kcal" -> switch (unit) {
                case "KILOCALORIE" -> value;
                case "JOULE", "J" -> value / 4184;
                case "KILOJOULE", "KJ" -> value / 4.184;
                case "CALORIE", "CAL" -> value / 1000;
                default -> incompatible(input, target);
            };
            case "kcal/d" -> switch (unit) {
                case "KILOCALORIE_PER_DAY", "KCAL/DAY" -> value;
                case "WATT", "W" -> value * 86400 / 4184;
                default -> incompatible(input, target);
            };
            default -> incompatible(input, target);
        };
    }

    private static double incompatible(String input, String target) {
        throw new IllegalArgumentException("Unit " + input + " cannot be converted to " + target);
    }
}
