package org.example.lineprotocol;

import com.google.gson.*;
import org.example.config.Environment;
import org.example.util.ConfigLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class LineProtocolParser {

    private static final Logger log = LoggerFactory.getLogger(LineProtocolParser.class);

    private static final String PATH_EFFECTIVE_DATE_TIME = "effectiveDateTime"; // implicit timestamp mapping

    private static final FhirLineProtocolConfig CONFIG = ConfigLoader.loadConfig(Environment.FHIR_LP_MAPPING_YAML_PATH, FhirLineProtocolConfig.class);

    private record MappingPattern(FhirLineProtocolConfig.Mapping raw, Pattern regex, boolean wildcard, boolean allowArray, String original) {}

    private static final List<MappingPattern> FIELD_PATTERNS = compilePatterns(CONFIG.getFieldMappings());
    private static final List<MappingPattern> TAG_PATTERNS = compilePatterns(CONFIG.getTagMappings());
    private static final MappingPattern MEASUREMENT_PATTERN = compilePatterns(List.of(CONFIG.getMeasurementMapping())).get(0);

    private static final MappingPattern TIMESTAMP_PATTERN = compilePatterns(List.of(CONFIG.getTimestampMapping())).get(0);

    private static List<MappingPattern> compilePatterns(List<FhirLineProtocolConfig.Mapping> mappings) {
        List<MappingPattern> list = new ArrayList<>();
        if (mappings == null) return list;
        for (FhirLineProtocolConfig.Mapping m : mappings) {
            if (m == null || m.getSource() == null || m.getSource().isBlank()) continue;
            String src = m.getSource().trim();
            boolean wildcard = src.contains("[x]");
            String regexStr = Pattern.quote(src).replace("\\[x\\]", "\\\\[\\\\d+\\\\]");
            Pattern p = Pattern.compile("^" + regexStr + "$");
            list.add(new MappingPattern(m, p, wildcard, m.isAllowArray(), src));
        }
        return list;
    }

    public String parse(String jsonString) throws IllegalArgumentException {
        if (jsonString == null || jsonString.isBlank()) {
            throw new IllegalArgumentException("Input JSON string is null or blank");
        }
        JsonElement rootEl = JsonParser.parseString(jsonString);
        if (!rootEl.isJsonObject()) throw new IllegalArgumentException("FHIR Observation must be a JSON object");
        JsonObject root = rootEl.getAsJsonObject();

        // Flatten all primitive paths
        Map<String, JsonPrimitive> primitives = new LinkedHashMap<>();
        collectPrimitives(root, "", primitives);

        // Measurement from config
        String measurement = extractSingle(MEASUREMENT_PATTERN, primitives);
        if (measurement == null || measurement.isBlank()) {
            throw new IllegalArgumentException("Measurement value not found for pattern: " + MEASUREMENT_PATTERN.original());
        }
        measurement = replaceSpaces(measurement);

        String timestamp = extractSingle(TIMESTAMP_PATTERN, primitives);
        if (timestamp == null || timestamp.isBlank()) {
            throw new IllegalArgumentException("Timestamp value not found for pattern: " + TIMESTAMP_PATTERN.original());
        }

        Long tsNanos = normalizeIsoToNanos(timestamp);

        // Fields
        LinkedHashMap<String, JsonPrimitive> fields = new LinkedHashMap<>();
        for (MappingPattern mp : FIELD_PATTERNS) {
            List<Map.Entry<String, JsonPrimitive>> matches = findMatches(mp, primitives);
            if (matches.isEmpty()) continue;
            if (!mp.allowArray && matches.size() > 1) {
                throw new IllegalArgumentException("Multiple values matched field pattern (allow-array=false): " + mp.original());
            }
            for (int i = 0; i < matches.size(); i++) {
                var e = matches.get(i);
                String key = deriveFieldKey(mp.original(), e.getKey(), i, matches.size());
                fields.put(key, e.getValue());
            }
        }
        if (fields.isEmpty()) throw new IllegalArgumentException("No fields produced by mapping configuration");

        // Tags
        TreeMap<String, String> tags = new TreeMap<>();
        for (MappingPattern mp : TAG_PATTERNS) {
            List<Map.Entry<String, JsonPrimitive>> matches = findMatches(mp, primitives);
            if (matches.isEmpty()) continue;
            if (!mp.allowArray && matches.size() > 1) {
                throw new IllegalArgumentException("Multiple values matched tag pattern (allow-array=false): " + mp.original());
            }
            for (int i = 0; i < matches.size(); i++) {
                var e = matches.get(i);
                String key = deriveTagKey(mp, e.getKey(), i, matches.size());
                String val = primitiveToString(e.getValue());
                if (val != null) tags.put(key, replaceSpaces(val));
            }
        }

        // Build line protocol
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

    private static List<Map.Entry<String, JsonPrimitive>> findMatches(MappingPattern pattern, Map<String, JsonPrimitive> primitives) {
        List<Map.Entry<String, JsonPrimitive>> list = new ArrayList<>();
        for (var e : primitives.entrySet()) {
            if (pattern.regex().matcher(e.getKey()).matches()) list.add(e);
        }
        if (pattern.wildcard()) list.sort(Comparator.comparing(Map.Entry::getKey));
        return list;
    }

    private static String extractSingle(MappingPattern pattern, Map<String, JsonPrimitive> primitives) {
        List<Map.Entry<String, JsonPrimitive>> matches = findMatches(pattern, primitives);
        if (matches.isEmpty()) return null;
        if (!pattern.allowArray() && matches.size() > 1) {
            throw new IllegalArgumentException("Multiple values matched single-value pattern: " + pattern.original());
        }
        return primitiveToString(matches.get(0).getValue());
    }

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

    private static String deriveFieldKey(String pattern, String matchedPath, int index, int total) {
        // Look up mapping to see if alias provided
        String alias = null;
        for (var mp : FIELD_PATTERNS) {
            if (mp.original().equals(pattern)) {
                alias = mp.raw().getAlias();
                break;
            }
        }
        if (pattern.endsWith("valueQuantity.value")) alias = (alias != null && !alias.isBlank()) ? alias : "value";
        if (pattern.endsWith("subject.reference")) alias = (alias != null && !alias.isBlank()) ? alias : "subject";
        if (pattern.endsWith("status")) alias = (alias != null && !alias.isBlank()) ? alias : "status";
        String base;
        if (alias != null && !alias.isBlank()) {
            base = alias;
        } else {
            base = pattern.replace("[x]", "");
            if (base.contains(".")) base = base.substring(base.lastIndexOf('.') + 1);
            base = base.replace('[', '_').replace(']', '_');
            base = base.replaceAll("__+", "_");
            if (base.endsWith("_")) base = base.substring(0, base.length() - 1);
        }
        if (total > 1) base = base + "_" + index;
        return base;
    }

    private static String deriveTagKey(MappingPattern mp, String matchedPath, int index, int total) {
        String alias = mp.raw().getAlias();
        String base;
        if (alias != null && !alias.isBlank()) {
            base = alias;
        } else {
            base = mp.original().replace("[x]", "");
            if (base.contains(".")) base = base.substring(base.lastIndexOf('.') + 1);
            base = base.replace('[', '_').replace(']', '_');
            base = base.replaceAll("__+", "_");
            if (base.endsWith("_")) base = base.substring(0, base.length() - 1);
        }
        // Add index suffix logic
        if (mp.wildcard()) {
            Matcher m = Pattern.compile("\\[(\\d+)\\]").matcher(matchedPath);
            String lastIdx = null;
            while (m.find()) lastIdx = m.group(1);
            if (lastIdx != null) base = base + "_" + lastIdx;
        } else if (total > 1) {
            base = base + "_" + index;
        }
        return base;
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
                    return raw + 'i';
                } catch (NumberFormatException ex) { /* fallback */ }
            }
            return raw;
        }
        String s = replaceSpaces(p.getAsString());
        String esc = s.replace("\\", "\\\\").replace("\"", "\\\"");
        return '"' + esc + '"';
    }
}
