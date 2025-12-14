package org.example.lineprotocol;

import com.google.gson.*;
import org.example.config.Environment;
import org.example.util.ConfigLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.*;

public class LineProtocolParser {

    private static final Logger log = LoggerFactory.getLogger(LineProtocolParser.class);

    private static final FhirLineProtocolConfig CONFIG = ConfigLoader.loadConfig(Environment.FHIR_LP_MAPPING_YAML_PATH, FhirLineProtocolConfig.class);
    private static final List<FhirLineProtocolConfig.Variant> VARIANTS = CONFIG.resolvedVariants();

    public String parse(String jsonString) throws IllegalArgumentException {
        if (jsonString == null || jsonString.isBlank()) {
            throw new IllegalArgumentException("Input JSON string is null or blank");
        }
        JsonElement rootEl = JsonParser.parseString(jsonString);
        if (!rootEl.isJsonObject()) throw new IllegalArgumentException("FHIR Observation must be a JSON object");
        JsonObject root = rootEl.getAsJsonObject();

        Map<String, JsonPrimitive> primitives = new LinkedHashMap<>();
        collectPrimitives(root, "", primitives);
        if (primitives.isEmpty()) throw new IllegalArgumentException("No primitive values found in observation");

        FhirLineProtocolConfig.Variant variant = selectVariant(primitives);
        if (variant == null) {
            throw new IllegalArgumentException("No mapping variant matched observation ");
        }

        return renderLineProtocol(primitives, variant);
    }

    private FhirLineProtocolConfig.Variant selectVariant(Map<String, JsonPrimitive> primitives) {
        for (FhirLineProtocolConfig.Variant variant : VARIANTS) {
            if (mappingResolvable(variant.getMeasurementMapping(), primitives)
                    && mappingResolvable(variant.getTimestampMapping(), primitives)) {
                return variant;
            }
        }
        return null;
    }

    private boolean mappingResolvable(FhirLineProtocolConfig.Mapping mapping, Map<String, JsonPrimitive> primitives) {
        return mapping != null && !findMatches(mapping, primitives).isEmpty();
    }

    private String renderLineProtocol(Map<String, JsonPrimitive> primitives, FhirLineProtocolConfig.Variant variant) {
        if (variant.getMeasurementMapping() == null) {
            throw new IllegalArgumentException("Variant missing measurement-mapping");
        }
        if (variant.getTimestampMapping() == null) {
            throw new IllegalArgumentException("Variant missing timestamp-mapping");
        }

        String measurement = extractSingle(variant.getMeasurementMapping(), primitives);
        if (measurement == null || measurement.isBlank()) {
            throw new IllegalArgumentException("Measurement value not found for source: " + variant.getMeasurementMapping().getSource());
        }
        measurement = replaceSpaces(measurement);

        String timestamp = extractSingle(variant.getTimestampMapping(), primitives);
        if (timestamp == null || timestamp.isBlank()) {
            throw new IllegalArgumentException("Timestamp value not found for source: " + variant.getTimestampMapping().getSource());
        }

        Long tsNanos = normalizeIsoToNanos(timestamp);

        LinkedHashMap<String, JsonPrimitive> fields = new LinkedHashMap<>();
        for (FhirLineProtocolConfig.Mapping fieldMapping : safeMappings(variant.getFieldMappings())) {
            List<Map.Entry<String, JsonPrimitive>> matches = findMatches(fieldMapping, primitives);
            if (matches.isEmpty()) continue;
            if (!fieldMapping.isAllowArray() && matches.size() > 1) {
                throw new IllegalArgumentException("Multiple values matched field mapping (allow-array=false): " + fieldMapping.getSource());
            }
            for (int i = 0; i < matches.size(); i++) {
                Map.Entry<String, JsonPrimitive> match = matches.get(i);
                String key = deriveKey(fieldMapping, match.getKey(), i, matches.size());
                fields.put(key, match.getValue());
            }
        }
        if (fields.isEmpty()) throw new IllegalArgumentException("No fields produced by mapping configuration");

        TreeMap<String, String> tags = new TreeMap<>();
        for (FhirLineProtocolConfig.Mapping tagMapping : safeMappings(variant.getTagMappings())) {
            List<Map.Entry<String, JsonPrimitive>> matches = findMatches(tagMapping, primitives);
            if (matches.isEmpty()) continue;
            if (!tagMapping.isAllowArray() && matches.size() > 1) {
                throw new IllegalArgumentException("Multiple values matched tag mapping (allow-array=false): " + tagMapping.getSource());
            }
            for (int i = 0; i < matches.size(); i++) {
                Map.Entry<String, JsonPrimitive> match = matches.get(i);
                String key = deriveKey(tagMapping, match.getKey(), i, matches.size());
                String val = primitiveToString(match.getValue());
                if (val != null) tags.put(key, replaceSpaces(val));
            }
        }

        StringBuilder sb = new StringBuilder();
        sb.append(escapeMeasurement(measurement));
        for (var e : tags.entrySet()) {
            sb.append(',').append(escapeKey(e.getKey())).append('=').append(escapeTagValue(e.getValue()));
        }
        sb.append(' ');
        boolean first = true;
        for (var e : fields.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(escapeKey(e.getKey())).append('=');
            sb.append(encodeFieldValue(e.getValue()));
        }
        if (tsNanos != null) sb.append(' ').append(tsNanos);
        return sb.toString();
    }

    private static List<FhirLineProtocolConfig.Mapping> safeMappings(List<FhirLineProtocolConfig.Mapping> mappings) {
        return mappings == null ? Collections.emptyList() : mappings;
    }

    private static List<Map.Entry<String, JsonPrimitive>> findMatches(FhirLineProtocolConfig.Mapping mapping, Map<String, JsonPrimitive> primitives) {
        if (mapping == null || mapping.getSource() == null || mapping.getSource().isBlank()) {
            return Collections.emptyList();
        }
        List<Map.Entry<String, JsonPrimitive>> matches = new ArrayList<>();
        boolean wildcard = mapping.getSource().contains("[x]");
        String normalized = wildcard ? mapping.getSource() : null;
        for (var entry : primitives.entrySet()) {
            String candidate = wildcard ? normalizePath(entry.getKey()) : entry.getKey();
            if (Objects.equals(candidate, wildcard ? normalized : mapping.getSource())) {
                matches.add(entry);
            }
        }
        return matches;
    }

    private static String extractSingle(FhirLineProtocolConfig.Mapping mapping, Map<String, JsonPrimitive> primitives) {
        List<Map.Entry<String, JsonPrimitive>> matches = findMatches(mapping, primitives);
        if (matches.isEmpty()) return null;
        if (!mapping.isAllowArray() && matches.size() > 1) {
            throw new IllegalArgumentException("Multiple values matched single-value mapping: " + mapping.getSource());
        }
        return primitiveToString(matches.get(0).getValue());
    }

    private static String normalizePath(String path) {
        return path.replaceAll("\\[(\\d+)\\]", "[x]");
    }

    //Iterate through the FHIR json and extract all primitive values (leafs) of it
    private static void collectPrimitives(JsonElement el, String path, Map<String, JsonPrimitive> out) {
        if (el == null || el.isJsonNull()) return;
        if (el.isJsonPrimitive()) {
            out.put(path, el.getAsJsonPrimitive());
            return;
        }
        if (el.isJsonArray()) {
            JsonArray arr = el.getAsJsonArray();
            for (int i = 0; i < arr.size(); i++) {
                String next = path.isEmpty() ? ("[" + i + "]") : (path + "[" + i + "]");
                collectPrimitives(arr.get(i), next, out);
            }
            return;
        }
        if (el.isJsonObject()) {
            for (var e : el.getAsJsonObject().entrySet()) {
                String next = path.isEmpty() ? e.getKey() : path + "." + e.getKey();
                collectPrimitives(e.getValue(), next, out);
            }
        }
    }

    private static String deriveKey(FhirLineProtocolConfig.Mapping mapping, String matchedPath, int index, int total) {
        String alias = mapping.getAlias();
        if (alias != null && !alias.isBlank()) {
            if (mapping.getSource().contains("[x]") && total > 1) {
                String idx = extractLastIndex(matchedPath);
                return idx == null ? alias + "_" + index : alias + "_" + idx;
            }
            return alias;
        }
        String base = mapping.getSource().replace("[x]", "");
        if (base.contains(".")) base = base.substring(base.lastIndexOf('.') + 1);
        base = base.replace('[', '_').replace(']', '_');
        while (base.endsWith("_")) base = base.substring(0, base.length() - 1);
        if (mapping.getSource().contains("[x]") && total > 1) {
            String idx = extractLastIndex(matchedPath);
            if (idx != null) base = base + "_" + idx;
            else base = base + "_" + index;
        } else if (total > 1) {
            base = base + "_" + index;
        }
        return base;
    }

    private static String extractLastIndex(String path) {
        int end = path.lastIndexOf(']');
        if (end == -1) return null;
        int start = path.lastIndexOf('[', end);
        if (start == -1 || start >= end) return null;
        String candidate = path.substring(start + 1, end);
        for (int i = 0; i < candidate.length(); i++) {
            if (!Character.isDigit(candidate.charAt(i))) return null;
        }
        return candidate;
    }

    private static String primitiveToString(JsonPrimitive p) {
        if (p == null) return null;
        if (p.isString()) return p.getAsString();
        if (p.isNumber()) return p.getAsString();
        if (p.isBoolean()) return String.valueOf(p.getAsBoolean());
        return null;
    }

    private static Long normalizeIsoToNanos(String str) {
        try {
            // Parse ISO 8601 string (handles Z or offset like +02:00)
            Instant instant = Instant.parse(str);
            // Convert to nanos since epoch
            return instant.getEpochSecond() * 1_000_000_000L + instant.getNano();
        } catch (Exception e) {
            throw new IllegalArgumentException("Invalid ISO 8601 datetime: " + str, e);
        }
    }

    private static String replaceSpaces(String in) {
        return in == null ? null : in.replace(' ', '_');
    }

    private static String escapeMeasurement(String in) {
        return replaceSpaces(in).replace("\\", "\\\\").replace(",", "\\,");
    }

    private static String escapeKey(String in) {
        return replaceSpaces(in).replace("\\", "\\\\").replace(",", "\\,").replace("=", "\\=");
    }

    private static String escapeTagValue(String in) {
        return replaceSpaces(in).replace("\\", "\\\\").replace(",", "\\,").replace("=", "\\=");
    }

    private static String encodeFieldValue(JsonPrimitive p) {
        if (p.isBoolean()) return String.valueOf(p.getAsBoolean());
        if (p.isNumber()) {
            String raw = p.getAsString();
            if (!raw.matches(".*[\\.eE].*")) {
                try {
                    Long.parseLong(raw);
                    return raw;
                } catch (NumberFormatException ex) { /* fallback */ }
            }
            return raw;
        }
        String s = replaceSpaces(p.getAsString());
        String esc = s.replace("\\", "\\\\").replace("\"", "\\\"");
        return '"' + esc + '"';
    }
}
