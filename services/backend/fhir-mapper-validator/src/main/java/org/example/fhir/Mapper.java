package org.example.fhir;

import com.google.gson.*;
import org.example.Main;
import org.example.config.Environment;
import org.example.util.ConfigLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class Mapper {

    private static final Logger log = LoggerFactory.getLogger(Mapper.class);

    final static MappingYaml yaml = ConfigLoader.loadConfig(Environment.MAPPING_YAML_PATH, MappingYaml.class);

    public static JsonObject mapFhir(String str) {

        if (yaml == null || yaml.getMappingsList() == null) {
            log.error("There was an error reading the mapping yaml");
            return null;
        }

        log.debug("Using yaml to transform: {}", yaml.getMappingsList().toString());
        JsonElement root = JsonParser.parseString(str);

        // Build mapping map from YAML: source -> (target, optional)
        java.util.Map<String, MappingRule> rules = buildSourceRuleMap(yaml);

        // Traverse input and build output according to rules
        JsonObject output = new JsonObject();
        java.util.Set<String> foundSources = new java.util.HashSet<>();
        traverseAndApply(root, "", output, rules, foundSources);

        // Verify that all non-optional mappings are present in input
        java.util.List<String> missingRequired = new java.util.ArrayList<>();
        for (java.util.Map.Entry<String, MappingRule> e : rules.entrySet()) {
            if (!e.getValue().optional && !foundSources.contains(e.getKey())) {
                missingRequired.add(e.getKey());
            }
        }
        if (!missingRequired.isEmpty()) {
            String msg = "Missing required fields in input for sources: " + missingRequired;
            log.error("{} | foundSources={} rules={}", msg, foundSources, rules.keySet());
            throw new RuntimeException(msg);
        }
        return output;
    }

    // Build a map from source path -> MappingRule (target, optional)
    static java.util.Map<String, MappingRule> buildSourceRuleMap(MappingYaml yamlCfg) {
        java.util.Map<String, MappingRule> map = new java.util.HashMap<>();
        if (yamlCfg == null || yamlCfg.getMappingsList() == null) return map;
        for (Mapping m : yamlCfg.getMappingsList()) {
            if (m == null) continue;
            String source = m.getSource() == null ? null : m.getSource().trim();
            if (source == null || source.isEmpty()) continue;
            String target = (m.getTarget() != null && !m.getTarget().trim().isEmpty()) ? m.getTarget().trim() : source;
            boolean optional = m.isOptional(); // defaults to false if missing
            MappingRule rule = new MappingRule(target, optional, ValueTransformer.identity());
            map.put(source, rule);
        }
        return map;
    }

    // Traverse input JSON and apply mapping rules where the current path matches a rule
    static void traverseAndApply(JsonElement element,
                                 String path,
                                 JsonObject out,
                                 java.util.Map<String, MappingRule> rules,
                                 java.util.Set<String> foundSources) {
        if (element == null || element.isJsonNull()) {
            if (!path.isEmpty() && rules.containsKey(path)) {
                MappingRule r = rules.get(path);
                log.debug("Applying mapping for null at path='{}' -> target='{}' (optional={})", path, r.target, r.optional);
                JsonElement transformed = r.transformer.apply(JsonNull.INSTANCE);
                setAtTarget(out, r.target, transformed);
                foundSources.add(path);
            }
            return;
        }
        if (element.isJsonPrimitive()) {
            if (!path.isEmpty() && rules.containsKey(path)) {
                MappingRule r = rules.get(path);
                log.debug("Applying mapping at primitive path='{}' -> target='{}' (optional={}) value={}", path, r.target, r.optional, element);
                JsonElement transformed = r.transformer.apply(element);
                setAtTarget(out, r.target, transformed);
                foundSources.add(path);
            }
            return;
        }
        if (element.isJsonArray()) {
            JsonArray arr = element.getAsJsonArray();
            for (int i = 0; i < arr.size(); i++) {
                String next = path.isEmpty() ? ("[" + i + "]") : (path + "[" + i + "]");
                traverseAndApply(arr.get(i), next, out, rules, foundSources);
            }
            return;
        }
        if (element.isJsonObject()) {
            JsonObject obj = element.getAsJsonObject();
            for (java.util.Map.Entry<String, JsonElement> e : obj.entrySet()) {
                String key = e.getKey();
                JsonElement child = e.getValue();
                String next = path.isEmpty() ? key : path + "." + key;
                traverseAndApply(child, next, out, rules, foundSources);
            }
        }
    }

    // Set a value inside the output JsonObject according to a dot/[index] path, creating structures as needed
    static void setAtTarget(JsonObject root, String targetPath, JsonElement value) {
        java.util.List<PathToken> tokens = tokenize(targetPath);
        if (tokens.isEmpty()) return;
        JsonElement current = root;
        for (int i = 0; i < tokens.size(); i++) {
            PathToken t = tokens.get(i);
            boolean last = (i == tokens.size() - 1);
            if (t instanceof FieldToken f) {
                JsonObject obj = current.getAsJsonObject();
                if (last) {
                    log.debug("setAtTarget: setting field '{}' with value={} (last token)", f.name, value);
                    obj.add(f.name, deepCopyElement(value));
                } else {
                    PathToken nextTok = tokens.get(i + 1);
                    JsonElement next = obj.get(f.name);
                    if (next == null || next.isJsonNull()) {
                        next = (nextTok instanceof IndexToken) ? new JsonArray() : new JsonObject();
                        obj.add(f.name, next);
                        log.debug("setAtTarget: created {} for field '{}'", (nextTok instanceof IndexToken) ? "JsonArray" : "JsonObject", f.name);
                    }
                    current = next;
                }
            } else if (t instanceof IndexToken idx) {
                // current should be a JsonArray here
                JsonArray arr;
                if (current.isJsonArray()) {
                    arr = current.getAsJsonArray();
                } else {
                    // Create array if current isn't array (edge case: target path starting with index)
                    arr = new JsonArray();
                    log.debug("setAtTarget: created JsonArray for index token at position {}", i);
                }
                while (arr.size() <= idx.index) arr.add(JsonNull.INSTANCE);
                if (last) {
                    log.debug("setAtTarget: setting array index {} with value={} (last token)", idx.index, value);
                    arr.set(idx.index, deepCopyElement(value));
                    current = arr.get(idx.index);
                } else {
                    PathToken nextTok = tokens.get(i + 1);
                    JsonElement next = arr.get(idx.index);
                    if (next == null || next.isJsonNull()) {
                        next = (nextTok instanceof IndexToken) ? new JsonArray() : new JsonObject();
                        arr.set(idx.index, next);
                        log.debug("setAtTarget: created {} at array index {}", (nextTok instanceof IndexToken) ? "JsonArray" : "JsonObject", idx.index);
                    }
                    current = next;
                }
            }
        }
    }

    static java.util.List<PathToken> tokenize(String path) {
        java.util.ArrayList<PathToken> tokens = new java.util.ArrayList<>();
        if (path == null || path.isBlank()) return tokens;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < path.length(); i++) {
            char c = path.charAt(i);
            if (c == '.') {
                if (sb.length() > 0) {
                    tokens.add(new FieldToken(sb.toString()));
                    sb.setLength(0);
                }
            } else if (c == '[') {
                if (sb.length() > 0) {
                    tokens.add(new FieldToken(sb.toString()));
                    sb.setLength(0);
                }
                int j = i + 1;
                int num = 0;
                while (j < path.length() && Character.isDigit(path.charAt(j))) {
                    num = num * 10 + (path.charAt(j) - '0');
                    j++;
                }
                // expect closing ']'
                if (j < path.length() && path.charAt(j) == ']') {
                    tokens.add(new IndexToken(num));
                    i = j; // advance
                } else {
                    // malformed, treat as literal
                    tokens.add(new FieldToken("["));
                }
            } else {
                sb.append(c);
            }
        }
        if (sb.length() > 0) {
            tokens.add(new FieldToken(sb.toString()));
        }
        return tokens;
    }

    static JsonElement deepCopyElement(JsonElement in) {
        if (in == null) return JsonNull.INSTANCE;
        try {
            return JsonParser.parseString(in.toString());
        } catch (Exception e) {
            return in; // fallback
        }
    }

    /**
     * @param transformer extensible hook for future transformations
     */ // Rule describing how to map a source path to a target path and whether it's optional.
    record MappingRule(String target, boolean optional, ValueTransformer transformer) {
        MappingRule(String target, boolean optional, ValueTransformer transformer) {
            this.target = target;
            this.optional = optional;
            this.transformer = transformer == null ? ValueTransformer.identity() : transformer;
        }
    }

    interface ValueTransformer {
        JsonElement apply(JsonElement in);

        static ValueTransformer identity() {
            return v -> v;
        }
    }

    static abstract class PathToken {
    }

    static final class FieldToken extends PathToken {
        final String name;

        FieldToken(String n) {
            this.name = n;
        }
    }

    static final class IndexToken extends PathToken {
        final int index;

        IndexToken(int i) {
            this.index = i;
        }
    }
}
