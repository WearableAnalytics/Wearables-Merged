package org.example.fhir;

import com.google.gson.*;
import org.example.config.Environment;
import org.example.fhir.model.FieldConfig;
import org.example.fhir.model.MappingRuleConfig;
import org.example.fhir.model.MeasurementConfig;
import org.example.fhir.model.MeasurementPathConfig;
import org.example.fhir.model.MetadataConfig;
import org.example.fhir.model.RuleConfig;
import org.example.util.ConfigLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Mapper {

    private static final Logger log = LoggerFactory.getLogger(Mapper.class);

    private static final MappingYaml TEMPLATE = ConfigLoader.loadConfig(Environment.MAPPING_YAML_PATH, MappingYaml.class);

    public static List<JsonObject> mapFhir(String str) {
        if (TEMPLATE == null) {
            throw new IllegalStateException("No mapping template loaded");
        }
        JsonElement parsed = JsonParser.parseString(str);
        if (!parsed.isJsonObject()) {
            throw new IllegalArgumentException("Incoming payload must be a JSON object");
        }
        JsonObject root = parsed.getAsJsonObject();
        JsonObject metadataTemplate = buildMetadataBlock(root);
        MeasurementConfig measurementCfg = TEMPLATE.getMeasurement();
        if (measurementCfg == null || measurementCfg.getPaths() == null || measurementCfg.getPaths().isEmpty()) {
            log.warn("No measurement paths configured – returning metadata-only document");
            return List.of(metadataTemplate.deepCopy());
        }
        List<JsonObject> observations = new ArrayList<>();
        for (MeasurementPathConfig pathConfig : measurementCfg.getPaths()) {
            if (pathConfig == null) continue;
            JsonArray measurementArray = resolveMeasurementArray(root, pathConfig.getPath());
            if (measurementArray == null) {
                log.warn("Measurement path '{}' not found or not an array", pathConfig.getPath());
                continue;
            }
            if (pathConfig.isArrayMapAll()) {
                for (int idx = 0; idx < measurementArray.size(); idx++) {
                    JsonElement measurementElement = measurementArray.get(idx);
                    JsonObject observation = metadataTemplate.deepCopy().getAsJsonObject();
                    applyFields(observation, TEMPLATE.getMetadata(), pathConfig, root, measurementElement, idx, true);
                    applyFields(observation, pathConfig, pathConfig, root, measurementElement, idx, true);
                    if (observation.size() > 0) observations.add(observation);
                }
            } else {
                Set<Integer> indexes = collectExplicitIndexes(pathConfig);
                for (Integer idx : indexes) {
                    if (idx < 0 || idx >= measurementArray.size()) {
                        log.warn("Index {} out of bounds for path '{}'", idx, pathConfig.getPath());
                        continue;
                    }
                    JsonElement measurementElement = measurementArray.get(idx);
                    JsonObject observation = metadataTemplate.deepCopy().getAsJsonObject();
                    applyFields(observation, TEMPLATE.getMetadata(), pathConfig, root, measurementElement, idx, false);
                    applyFields(observation, pathConfig, pathConfig, root, measurementElement, idx, false);
                    if (observation.size() > 0) observations.add(observation);
                }
            }
        }
        return observations;
    }

    private static JsonObject buildMetadataBlock(JsonObject root) {
        JsonObject metadata = new JsonObject();
        MetadataConfig metadataConfig = TEMPLATE.getMetadata();
        applyFields(metadata, metadataConfig, null, root, null, -1, false);
        return metadata;
    }

    private static JsonArray resolveMeasurementArray(JsonObject root, String path) {
        if (path == null || path.isBlank()) return null;
        JsonElement el = getByPath(root, path);
        if (el == null || !el.isJsonArray()) return null;
        return el.getAsJsonArray();
    }

    private static void applyFields(JsonObject target,
                                    MetadataConfig metadataCfg,
                                    MeasurementPathConfig measurementCfg,
                                    JsonObject root,
                                    JsonElement measurementElement,
                                    int measurementIndex,
                                    boolean arrayMapAll) {
        if (metadataCfg == null || metadataCfg.getFields() == null) return;
        for (FieldConfig field : metadataCfg.getFields()) {
            applySingleField(target, field, measurementCfg, root, measurementElement, measurementIndex, arrayMapAll);
        }
    }

    private static void applyFields(JsonObject target,
                                    MeasurementPathConfig fieldCfg,
                                    MeasurementPathConfig measurementCfg,
                                    JsonObject root,
                                    JsonElement measurementElement,
                                    int measurementIndex,
                                    boolean arrayMapAll) {
        if (fieldCfg == null || fieldCfg.getFields() == null) return;
        for (FieldConfig field : fieldCfg.getFields()) {
            applySingleField(target, field, measurementCfg, root, measurementElement, measurementIndex, arrayMapAll);
        }
    }

    private static void applySingleField(JsonObject target,
                                         FieldConfig field,
                                         MeasurementPathConfig measurementCfg,
                                         JsonObject root,
                                         JsonElement measurementElement,
                                         int measurementIndex,
                                         boolean arrayMapAll) {
        if (field == null) return;
        if (field.getTarget() == null || field.getTarget().isBlank()) {
            log.warn("Skipping field '{}' because target is missing", field.getName());
            return;
        }
        JsonElement value;
        if (field.isMapping()) {
            value = resolveMappingValue(field, measurementCfg, root, measurementElement, measurementIndex, arrayMapAll);
        } else if (field.getValue() != null) {
            value = toJsonElement(field.getValue());
        } else {
            String sourcePath = field.getSource();
            if (sourcePath == null || sourcePath.isBlank()) {
                if (!field.isOptional()) {
                    throw new IllegalStateException("Field '" + field.getName() + "' lacks a source/value but is required");
                }
                return;
            }
            String expanded = expandPathForMeasurement(sourcePath, measurementCfg, measurementIndex, arrayMapAll);
            JsonElement resolved = getByPath(root, expanded);
            if ((resolved == null || resolved.isJsonNull()) && measurementElement != null && measurementCfg != null) {
                String relative = deriveRelativePath(sourcePath, measurementCfg.getPath());
                if (relative != null) {
                    resolved = relative.isEmpty() ? measurementElement : getByPath(measurementElement, relative);
                }
            }
            value = resolved;
        }
        if (value == null || value.isJsonNull()) {
            if (!field.isOptional()) {
                throw new IllegalStateException("Missing required field '" + field.getName() + "' for target " + field.getTarget());
            }
            return;
        }
        setAtTarget(target, field.getTarget(), deepCopyElement(value));
    }

    private static JsonElement resolveMappingValue(FieldConfig field,
                                                   MeasurementPathConfig measurementCfg,
                                                   JsonObject root,
                                                   JsonElement measurementElement,
                                                   int measurementIndex,
                                                   boolean arrayMapAll) {
        if (measurementCfg == null || measurementCfg.getMappings() == null) {
            log.warn("Field '{}' flagged as mapping but no mappings configured", field.getName());
            return null;
        }
        MappingRuleConfig ruleConfig = measurementCfg.getMappings().stream()
                .filter(rule -> rule != null && Objects.equals(rule.getPath(), field.getTarget()))
                .findFirst()
                .orElse(null);
        if (ruleConfig == null) {
            log.warn("No mapping rule found for target '{}'", field.getTarget());
            return null;
        }
        String basedOnPath = expandPathForMeasurement(ruleConfig.getBasedOn(), measurementCfg, measurementIndex, arrayMapAll);
        JsonElement basedOnValue = getByPath(root, basedOnPath);
        if ((basedOnValue == null || basedOnValue.isJsonNull()) && measurementElement != null) {
            String relative = deriveRelativePath(ruleConfig.getBasedOn(), measurementCfg.getPath());
            if (relative != null) {
                basedOnValue = relative.isEmpty() ? measurementElement : getByPath(measurementElement, relative);
            }
        }
        if (basedOnValue == null || basedOnValue.isJsonNull()) {
            log.warn("Mapping rule for '{}' missing basedOn value at path '{}'", field.getTarget(), ruleConfig.getBasedOn());
            return null;
        }
        String key = primitiveAsString(basedOnValue);
        if (key == null) {
            log.warn("Mapping rule for '{}' could not convert basedOn value to string", field.getTarget());
            return null;
        }
        List<RuleConfig> rules = ruleConfig.getMap();
        if (rules == null) {
            log.warn("Mapping rule for '{}' has no map entries", field.getTarget());
            return null;
        }
        for (RuleConfig rule : rules) {
            if (rule != null && Objects.equals(rule.getKey(), key)) {
                return toJsonElement(rule.getValue());
            }
        }
        log.warn("Mapping rule for '{}' does not contain key '{}'", field.getTarget(), key);
        return null;
    }

    private static Set<Integer> collectExplicitIndexes(MeasurementPathConfig pathConfig) {
        Set<Integer> indexes = new LinkedHashSet<>();
        if (pathConfig == null || pathConfig.getFields() == null) return indexes;
        String alias = measurementAlias(pathConfig.getPath());
        Pattern mainPattern = Pattern.compile(Pattern.quote(pathConfig.getPath()) + "\\[(\\d+)]");
        Pattern aliasPattern = alias == null ? null : Pattern.compile(Pattern.quote(alias) + "\\[(\\d+)]");
        for (FieldConfig field : pathConfig.getFields()) {
            if (field == null || field.getSource() == null) continue;
            Matcher matcher = mainPattern.matcher(field.getSource());
            while (matcher.find()) {
                indexes.add(Integer.parseInt(matcher.group(1)));
            }
            if (aliasPattern != null) {
                Matcher aliasMatcher = aliasPattern.matcher(field.getSource());
                while (aliasMatcher.find()) {
                    indexes.add(Integer.parseInt(aliasMatcher.group(1)));
                }
            }
        }
        return indexes;
    }

    private static String expandPathForMeasurement(String rawPath,
                                                   MeasurementPathConfig measurementCfg,
                                                   int measurementIndex,
                                                   boolean arrayMapAll) {
        if (rawPath == null || measurementCfg == null) return rawPath;
        String measurementPath = measurementCfg.getPath();
        if (measurementPath == null || measurementPath.isBlank()) return rawPath;
        String alias = measurementAlias(measurementPath);
        String expanded = rawPath;
        if (alias != null && expanded.startsWith(alias)) {
            expanded = measurementPath + expanded.substring(alias.length());
        }
        if (!expanded.startsWith(measurementPath)) {
            return expanded;
        }
        if (!arrayMapAll) {
            return expanded;
        }
        int prefixLen = measurementPath.length();
        if (expanded.length() > prefixLen && expanded.charAt(prefixLen) == '[') {
            return expanded;
        }
        return measurementPath + "[" + measurementIndex + "]" + expanded.substring(prefixLen);
    }

    private static String deriveRelativePath(String rawPath, String measurementPath) {
        if (rawPath == null || measurementPath == null) return null;
        String alias = measurementAlias(measurementPath);
        if (rawPath.startsWith(measurementPath)) {
            return stripLeadingDot(rawPath.substring(measurementPath.length()));
        }
        if (alias != null && rawPath.startsWith(alias)) {
            return stripLeadingDot(rawPath.substring(alias.length()));
        }
        return null;
    }

    private static String stripLeadingDot(String value) {
        if (value == null) return null;
        if (value.startsWith(".")) {
            return value.substring(1);
        }
        return value;
    }

    private static String measurementAlias(String path) {
        if (path == null || path.isBlank()) return null;
        int dot = path.indexOf('.')
;
        if (dot < 0) {
            return path.endsWith("s") ? path.substring(0, path.length() - 1) : path;
        }
        String first = path.substring(0, dot);
        if (first.endsWith("s")) first = first.substring(0, first.length() - 1);
        return first + path.substring(dot);
    }

    private static JsonElement getByPath(JsonElement root, String path) {
        if (root == null || path == null || path.isBlank()) return null;
        List<PathToken> tokens = tokenize(path);
        JsonElement current = root;
        for (PathToken token : tokens) {
            if (current == null || current.isJsonNull()) return null;
            if (token instanceof FieldToken field) {
                if (!current.isJsonObject()) return null;
                current = current.getAsJsonObject().get(field.name);
            } else if (token instanceof IndexToken indexToken) {
                if (!current.isJsonArray()) return null;
                JsonArray arr = current.getAsJsonArray();
                if (indexToken.index < 0 || indexToken.index >= arr.size()) return null;
                current = arr.get(indexToken.index);
            }
        }
        return current;
    }

    static void setAtTarget(JsonObject root, String targetPath, JsonElement value) {
        List<PathToken> tokens = tokenize(targetPath);
        if (tokens.isEmpty()) return;
        JsonElement current = root;
        for (int i = 0; i < tokens.size(); i++) {
            PathToken token = tokens.get(i);
            boolean last = (i == tokens.size() - 1);
            if (token instanceof FieldToken field) {
                JsonObject obj = current.getAsJsonObject();
                if (last) {
                    obj.add(field.name, deepCopyElement(value));
                } else {
                    JsonElement next = obj.get(field.name);
                    if (next == null || next.isJsonNull()) {
                        next = tokens.get(i + 1) instanceof IndexToken ? new JsonArray() : new JsonObject();
                        obj.add(field.name, next);
                    }
                    current = next;
                }
            } else if (token instanceof IndexToken indexToken) {
                JsonArray arr;
                if (current.isJsonArray()) {
                    arr = current.getAsJsonArray();
                } else {
                    arr = new JsonArray();
                }
                while (arr.size() <= indexToken.index) {
                    arr.add(JsonNull.INSTANCE);
                }
                if (last) {
                    arr.set(indexToken.index, deepCopyElement(value));
                } else {
                    JsonElement next = arr.get(indexToken.index);
                    if (next == null || next.isJsonNull()) {
                        next = tokens.get(i + 1) instanceof IndexToken ? new JsonArray() : new JsonObject();
                        arr.set(indexToken.index, next);
                    }
                    current = next;
                }
            }
        }
    }

    static List<PathToken> tokenize(String path) {
        ArrayList<PathToken> tokens = new ArrayList<>();
        if (path == null || path.isBlank()) return tokens;
        StringBuilder current = new StringBuilder();
        for (int i = 0; i < path.length(); i++) {
            char c = path.charAt(i);
            if (c == '.') {
                if (current.length() > 0) {
                    tokens.add(new FieldToken(current.toString()));
                    current.setLength(0);
                }
            } else if (c == '[') {
                if (current.length() > 0) {
                    tokens.add(new FieldToken(current.toString()));
                    current.setLength(0);
                }
                int j = i + 1;
                int number = 0;
                while (j < path.length() && Character.isDigit(path.charAt(j))) {
                    number = number * 10 + (path.charAt(j) - '0');
                    j++;
                }
                if (j < path.length() && path.charAt(j) == ']') {
                    tokens.add(new IndexToken(number));
                    i = j;
                }
            } else {
                current.append(c);
            }
        }
        if (current.length() > 0) {
            tokens.add(new FieldToken(current.toString()));
        }
        return tokens;
    }

    static JsonElement deepCopyElement(JsonElement in) {
        if (in == null) return JsonNull.INSTANCE;
        try {
            return JsonParser.parseString(in.toString());
        } catch (Exception e) {
            return in;
        }
    }

    static JsonElement toJsonElement(Object value) {
        if (value == null) return JsonNull.INSTANCE;
        if (value instanceof JsonElement jsonElement) return jsonElement;
        if (value instanceof String string) return new JsonPrimitive(string);
        if (value instanceof Number number) return new JsonPrimitive(number);
        if (value instanceof Boolean bool) return new JsonPrimitive(bool);
        return new Gson().toJsonTree(value);
    }

    private static String primitiveAsString(JsonElement element) {
        if (element == null || element.isJsonNull()) return null;
        if (element.isJsonPrimitive()) return element.getAsJsonPrimitive().getAsString();
        return element.toString();
    }

    static abstract class PathToken { }

    static final class FieldToken extends PathToken {
        final String name;
        FieldToken(String name) {
            this.name = name;
        }
    }

    static final class IndexToken extends PathToken {
        final int index;
        IndexToken(int index) {
            this.index = index;
        }
    }
}
