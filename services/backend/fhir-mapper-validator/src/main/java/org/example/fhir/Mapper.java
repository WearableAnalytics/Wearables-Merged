package org.example.fhir;

import com.google.gson.*;
import org.example.config.Environment;
import org.example.util.ConfigLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Mapper converts an incoming FHIR JSON payload into another JSON structure
 * according to a declarative YAML mapping. The YAML provides a list of
 * source JSON paths (dot-notation with optional [index] for arrays) and
 * target JSON paths for where to write the values.
 *
 * High-level flow:
 * 1) Load the mapping YAML once at class load (via ConfigLoader + env var).
 * 2) Build a rules map: sourcePath -> MappingRule(targetPath, optional, transformer).
 * 3) Traverse the input JSON depth-first, and whenever the current path matches a rule,
 *    write the (optionally transformed) value to the target path of the output JSON.
 * 4) Track which source paths were found and error if any required mapping is missing.
 */
public class Mapper {

    private static final Logger log = LoggerFactory.getLogger(Mapper.class);

    // Load YAML once. Environment.MAPPING_YAML_PATH points to the file path env var name.
    // ConfigLoader.loadConfig handles reading and deserializing the YAML to MappingYaml.
    final static MappingYaml yaml = ConfigLoader.loadConfig(Environment.MAPPING_YAML_PATH, MappingYaml.class);

    /**
     * Map the provided FHIR JSON string into a new JSON object based on the mapping YAML.
     *
     * Contract:
     * - Input: a valid JSON object string (FHIR resource).
     * - Output: a JsonObject populated according to the YAML rules.
     * - Required (non-optional) rules must be present in the input; otherwise an error is thrown.
     *
     * @param str the incoming FHIR JSON string
     * @return a JsonObject with values written to their target paths; null if YAML failed to load
     * @throws RuntimeException if a required mapping is missing in the input
     */
    public static JsonObject mapFhir(String str) {

        if (yaml == null || yaml.getMappingsList() == null) {
            log.error("There was an error reading the mapping yaml");
            return null;
        }

        log.debug("Using yaml to transform: {}", yaml.getMappingsList());
        JsonElement root = JsonParser.parseString(str);

        // Build mapping map from YAML: sourcePath -> rule(targetPath, optional)
        // Using a HashMap for O(1) lookups when we visit paths during traversal.
        java.util.Map<String, MappingRule> rules = buildSourceRuleMap(yaml);
        // Also collect constant (target,value) rules that don't depend on input
        java.util.List<MappingRule> constantRules = buildConstantRules(yaml);

        // We traverse the input once and build the output incrementally.
        JsonObject output = new JsonObject();
        // Track which source paths were actually found in the input to verify required mappings.
        java.util.Set<String> foundSources = new java.util.HashSet<>();
        traverseAndApply(root, "", output, rules, foundSources);

        // After traversal, verify that all non-optional (required) mappings were matched.
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

        // Apply constant rules last so they can override values if desired
        for (MappingRule constRule : constantRules) {
            log.debug("Applying constant mapping: target='{}' value={} (optional={})", constRule.target, constRule.constantValue, constRule.optional);
            setAtTarget(output, constRule.target, deepCopyElement(constRule.constantValue));
        }
        return output;
    }

    /**
     * Build a lookup table from source JSON path to a MappingRule describing
     * the target path and whether the mapping is optional.
     *
     * Path syntax:
     * - Dot notation for object fields: a.b.c
     * - Array index with square brackets: a[0].b
     *
     * @param yamlCfg the parsed YAML configuration
     * @return map of source path -> rule
     */
    static java.util.Map<String, MappingRule> buildSourceRuleMap(MappingYaml yamlCfg) {
        java.util.Map<String, MappingRule> map = new java.util.HashMap<>();
        if (yamlCfg == null || yamlCfg.getMappingsList() == null) return map;
        for (Mapping m : yamlCfg.getMappingsList()) {
            if (m == null) continue;
            // If a constant value is supplied, this mapping is handled by buildConstantRules
            if (m.getValue() != null) continue;

            String source = m.getSource() == null ? null : m.getSource().trim();
            if (source == null || source.isEmpty()) continue;
            // If target is omitted, default to the same path as source
            String target = (m.getTarget() != null && !m.getTarget().trim().isEmpty()) ? m.getTarget().trim() : source;
            boolean optional = m.isOptional(); // defaults to false if missing
            MappingRule rule = new MappingRule(target, optional, ValueTransformer.identity(), null);
            map.put(source, rule);
        }
        return map;
    }

    /**
     * Build constant (target,value) rules from YAML. These do not depend on any source path.
     * If a mapping has both source and value, value wins and the source is ignored.
     */
    static java.util.List<MappingRule> buildConstantRules(MappingYaml yamlCfg) {
        java.util.List<MappingRule> list = new java.util.ArrayList<>();
        if (yamlCfg == null || yamlCfg.getMappingsList() == null) return list;
        for (Mapping m : yamlCfg.getMappingsList()) {
            if (m == null) continue;
            if (m.getValue() == null) continue; // only collect mappings with a literal value

            String target = (m.getTarget() != null && !m.getTarget().trim().isEmpty()) ? m.getTarget().trim() : null;
            if (target == null) {
                log.warn("Constant mapping skipped: 'target' is required when 'value' is provided. Mapping={}.", m);
                continue;
            }
            boolean optional = m.isOptional();
            JsonElement constElem = toJsonElement(m.getValue());
            list.add(new MappingRule(target, optional, ValueTransformer.identity(), constElem));
        }
        return list;
    }

    /**
     * Depth-first traversal over the input JSON. For each leaf value, we compare its path
     * (constructed via dot notation and [index] for arrays) against the rule map. When there
     * is a match, we write the value (possibly transformed) to the corresponding target path
     * in the output object.
     *
     * @param element current input node
     * @param path    current JSON path (dot/[index] notation)
     * @param out     output JSON object to populate
     * @param rules   mapping rules (source path -> rule)
     * @param foundSources set of source paths that were actually matched (for required-field checking)
     */
    static void traverseAndApply(JsonElement element,
                                 String path,
                                 JsonObject out,
                                 java.util.Map<String, MappingRule> rules,
                                 java.util.Set<String> foundSources) {
        // When the current element is null, we still consider mapping if the path is explicitly mapped.
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
        // For primitives, apply mapping if current path is configured.
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
        // For arrays, recurse with [index] segment appended to path (e.g., items[0]).
        if (element.isJsonArray()) {
            JsonArray arr = element.getAsJsonArray();
            for (int i = 0; i < arr.size(); i++) {
                String next = path.isEmpty() ? ("[" + i + "]") : (path + "[" + i + "]");
                traverseAndApply(arr.get(i), next, out, rules, foundSources);
            }
            return;
        }
        // For objects, recurse with ".field" appended to the path.
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

    /**
     * Write a value into the output JsonObject at the given target path, creating
     * intermediate objects/arrays as needed. The target path uses the same dot/[index]
     * notation as source paths, so this method tokenizes the path and walks/creates
     * the structure until the last token, where it writes the value.
     *
     * @param root       the output object to mutate
     * @param targetPath path to write to (e.g., a.b[0].c)
     * @param value      value to set (deep-copied to avoid aliasing)
     */
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
                        // Decide whether to create an object or array depending on the next token type
                        next = (nextTok instanceof IndexToken) ? new JsonArray() : new JsonObject();
                        obj.add(f.name, next);
                        log.debug("setAtTarget: created {} for field '{}'", (nextTok instanceof IndexToken) ? "JsonArray" : "JsonObject", f.name);
                    }
                    current = next;
                }
            } else if (t instanceof IndexToken idx) {
                // current should be a JsonArray here; create one if not present
                JsonArray arr;
                if (current.isJsonArray()) {
                    arr = current.getAsJsonArray();
                } else {
                    arr = new JsonArray();
                    log.debug("setAtTarget: created JsonArray for index token at position {}", i);
                }
                // Ensure the array has enough capacity (fill gaps with nulls)
                while (arr.size() <= idx.index) arr.add(JsonNull.INSTANCE);
                if (last) {
                    log.debug("setAtTarget: setting array index {} with value={} (last token)", idx.index, value);
                    arr.set(idx.index, deepCopyElement(value));
                    current = arr.get(idx.index);
                } else {
                    PathToken nextTok = tokens.get(i + 1);
                    JsonElement next = arr.get(idx.index);
                    if (next == null || next.isJsonNull()) {
                        // Create nested container appropriate for the next token
                        next = (nextTok instanceof IndexToken) ? new JsonArray() : new JsonObject();
                        arr.set(idx.index, next);
                        log.debug("setAtTarget: created {} at array index {}", (nextTok instanceof IndexToken) ? "JsonArray" : "JsonObject", idx.index);
                    }
                    current = next;
                }
            }
        }
    }

    /**
     * Tokenize a dot/[index] path into a list of tokens for easier navigation and mutation.
     * Examples:
     * - "a.b[0].c" -> [FieldToken("a"), FieldToken("b"), IndexToken(0), FieldToken("c")]
     * - "[0]" -> [IndexToken(0)]
     *
     * @param path a dot/[index] path string
     * @return ordered tokens representing the path
     */
    static java.util.List<PathToken> tokenize(String path) {
        java.util.ArrayList<PathToken> tokens = new java.util.ArrayList<>();
        if (path == null || path.isBlank()) return tokens;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < path.length(); i++) {
            char c = path.charAt(i);
            if (c == '.') {
                // Flush the accumulated field name on dot
                if (sb.length() > 0) {
                    tokens.add(new FieldToken(sb.toString()));
                    sb.setLength(0);
                }
            } else if (c == '[') {
                // Push any pending field before processing the index
                if (sb.length() > 0) {
                    tokens.add(new FieldToken(sb.toString()));
                    sb.setLength(0);
                }
                int j = i + 1;
                int num = 0;
                while (j < path.length() && Character.isDigit(path.charAt(j))) {
                    //reconstruct number in the decimal system
                    num = num * 10 + (path.charAt(j) - '0');
                    j++;
                }
                // expect closing ']'
                if (j < path.length() && path.charAt(j) == ']') {
                    tokens.add(new IndexToken(num));
                    i = j; // advance past ']'
                } else {
                    // malformed index; treat it as a literal field to avoid crashing
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

    /**
     * Create a defensive deep copy of a JsonElement. Gson elements are mutable and shared
     * references could lead to unexpected aliasing. This method uses JSON serialization
     * round-trip via parsing the element's string to create a new instance.
     *
     * @param in element to copy (may be null)
     * @return an equivalent JsonElement instance, or JsonNull if input is null
     */
    static JsonElement deepCopyElement(JsonElement in) {
        if (in == null) return JsonNull.INSTANCE;
        try {
            // Cheap deep copy by re-parsing the JSON representation
            return JsonParser.parseString(in.toString());
        } catch (Exception e) {
            // Fallback to the original element if parsing fails
            return in;
        }
    }

    /**
     * Convert an arbitrary Java object (read from YAML) into a Gson JsonElement.
     * Supports primitives (String, Number, Boolean), nulls, and complex types (Map/List).
     */
    static JsonElement toJsonElement(Object o) {
        if (o == null) return JsonNull.INSTANCE;
        if (o instanceof String s) return new JsonPrimitive(s);
        if (o instanceof Number n) return new JsonPrimitive(n);
        if (o instanceof Boolean b) return new JsonPrimitive(b);
        // For arrays/objects, delegate to Gson toJsonTree
        return new Gson().toJsonTree(o);
    }

    /**
     * Rule describing how to map a source path to a target path and whether it's optional.
     * A ValueTransformer hook is included for future transformations (e.g., type conversions,
     * formatting). If constantValue is non-null, this rule represents a constant mapping.
     */
    record MappingRule(String target, boolean optional, ValueTransformer transformer, JsonElement constantValue) {
        MappingRule(String target, boolean optional, ValueTransformer transformer) {
            this(target, optional, transformer, null);
        }
    }

    /**
     * Hook to transform values before writing them to the output JSON.
     * Currently only identity() is used, but custom logic could be added later.
     */
    interface ValueTransformer {
        JsonElement apply(JsonElement in);

        static ValueTransformer identity() {
            return v -> v;
        }
    }

    // Marker type for path tokens (field vs index)
    static abstract class PathToken { }

    // Field access token (e.g., ".name")
    static final class FieldToken extends PathToken {
        final String name;
        FieldToken(String n) { this.name = n; }
    }

    // Array index token (e.g., "[3]")
    static final class IndexToken extends PathToken {
        final int index;
        IndexToken(int i) { this.index = i; }
    }
}
