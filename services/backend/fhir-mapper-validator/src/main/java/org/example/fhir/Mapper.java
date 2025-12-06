package org.example.fhir;

import com.google.gson.*;
import org.example.config.Environment;
import org.example.fhir.model.*;
import org.example.util.ConfigLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import static org.example.fhir.Transformations.*;

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
        JsonObject incoming = parsed.getAsJsonObject();
        JsonObject metadataTemplate = buildMetadataBlock(incoming);
        MeasurementConfig measurementCfg = TEMPLATE.getMeasurement();
        if (measurementCfg == null || measurementCfg.getPaths() == null || measurementCfg.getPaths().isEmpty()) {
            log.warn("No measurement paths configured – returning metadata-only document");
            return List.of(metadataTemplate.deepCopy());
        }
        List<JsonObject> observations = new ArrayList<>();
        for (MeasurementPathConfig pathConfig : measurementCfg.getPaths()) {
            if (pathConfig == null) continue;
            //measurement array is one array of measurements inside the incoming json (e.g., cumulative, period, instantaneous)
            JsonArray measurementArray = resolveMeasurementArray(incoming, pathConfig.getPath());
            if (measurementArray == null) {
                log.warn("Measurement path '{}' not found or not an array", pathConfig.getPath());
                continue;
            }
            if (pathConfig.isArrayMapAll()) {
                for (int idx = 0; idx < measurementArray.size(); idx++) {
                    JsonElement measurementElement = measurementArray.get(idx);
                    JsonObject template = metadataTemplate.deepCopy().getAsJsonObject();
                    log.debug("Template is {}", template);
                    log.debug("Incoming is {} and we are looking at {}", incoming, measurementElement);
                    applyFields(template, TEMPLATE.getMetadata(), pathConfig, incoming, measurementElement, idx);
                    log.debug("Template after metadata is {}", template);
                    log.debug("Incoming after metadata is {} and we are looking at {}", incoming, measurementElement);
                    applyFields(template, pathConfig, pathConfig, incoming, measurementElement, idx);
                    if (!template.isEmpty()) observations.add(template);
                }
            } else {
                throw new RuntimeException("Mapping of only a subset of measurements is not yet supported");
                //TODO implement filtering function to decide what to map instead of index based
            }
        }
        return observations;
    }

    private static JsonObject buildMetadataBlock(JsonObject root) {
        JsonObject metadata = new JsonObject();
        MetadataConfig metadataConfig = TEMPLATE.getMetadata();
        applyFields(metadata, metadataConfig, null, root, null, -1);
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
                                    int idx) {
        if (metadataCfg.getFields() == null) return;
        for (FieldConfig field : metadataCfg.getFields()) {
            applySingleField(target, field, measurementCfg, root, measurementElement, idx);
        }
    }

    private static void applyFields(JsonObject target,
                                    MeasurementPathConfig fieldCfg,
                                    MeasurementPathConfig measurementCfg,
                                    JsonObject root,
                                    JsonElement measurementElement,
                                    int idx) {
        if (fieldCfg == null || fieldCfg.getFields() == null) return;
        for (FieldConfig field : fieldCfg.getFields()) {
            applySingleField(target, field, measurementCfg, root, measurementElement, idx);
        }
    }

    private static void applySingleField(JsonObject outgoingElementTemplate,
                                         FieldConfig field,
                                         MeasurementPathConfig measurementCfg,
                                         JsonObject rootOfIncoming,
                                         JsonElement measurementElement,
                                         int idx) {
        if (field == null) return;
        if (field.getTarget() == null || field.getTarget().isBlank()) {
            log.warn("Skipping field '{}' because outgoingElementTemplate is missing", field.getName());
            return;
        }
        JsonElement value;
        if (field.getTransform() != null && !field.getTransform().isEmpty()) {
            log.debug("found field that needs to be transformed: {}", field.getName());
            value = resolveTransformationField(field, measurementCfg, rootOfIncoming, measurementElement, idx);
        } else if (field.getValue() != null) {
            log.debug("found field that needs to be retrieved from value: {}", field.getName());
            value = toJsonElement(field.getValue());
        } else {
            log.debug("found field {} that needs to be retrieved from source: {}", field.getName(), field.getSource());
            String sourcePath = expandPathForMeasurement(field.getSource(), measurementCfg, idx);
            if (sourcePath == null || sourcePath.isBlank()) {
                if (!field.isOptional()) {
                    throw new IllegalStateException("Field '" + field.getName() + "' lacks a source/value but is required");
                }
                return;
            }
            JsonElement resolved = getByPath(rootOfIncoming, sourcePath);
            //resolve = one field inside one measurement object in json //measurementElement = said measurement object
            //--> i think if measurementElement is null, resolved must also be null since its parent element does not exist
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
        setAtTarget(outgoingElementTemplate, field.getTarget(), deepCopyElement(value));
    }

    private static JsonElement resolveTransformationField(
            FieldConfig field,
            MeasurementPathConfig measurementCfg,
            JsonObject root,
            JsonElement measurementElement,
            int idx
    ) {

        String indexedPath = expandPathForMeasurement(field.getSource(), measurementCfg, idx);
        JsonElement value = getByPath(root, indexedPath);

        log.debug(
                "retrieved source for field {}: {}; it has {} number of mappings",
                field.getName(), field.getSource(), field.getTransform().size()
        );

        // apply transformations in the order they were listed
        for (ValueTransformation vt : field.getTransform()) {

            String type = vt.getType();
            log.debug("mapping field {} with rule {}", field.getName(), type);

            if (value == null && !Objects.equals(type, "mapBasedOn")) {
                log.warn("field {} transformation '{}' skipped because value is null", field.getName(), type);
                return null;
            }

            switch (type) {

                case "toLowerCase": {
                    if (vt.getParams() != null && !vt.getParams().isEmpty())
                        log.warn("arguments are not allowed for 'toLowerCase' and will be ignored");

                    String s = elementToString(value);
                    if (s == null)
                        throw new RuntimeException(
                                String.format("value for toLowerCase [%s] could not be converted to string", value)
                        );

                    value = toJsonElement(s.toLowerCase());
                    break;
                }

                case "replace": {
                    if (vt.getParams() == null || vt.getParams().size() != 2) {
                        log.warn("there must be exactly two arguments for 'replace'");
                        return null;
                    }

                    String s = elementToString(value);
                    if (s == null)
                        throw new RuntimeException(
                                String.format("value for replace [%s] could not be converted to string", value)
                        );

                    value = toJsonElement(
                            s.replace(vt.getParams().get(0), vt.getParams().get(1))
                    );
                    break;
                }

                case "append": {
                    String s = elementToString(value);
                    if (s == null)
                        throw new RuntimeException(
                                String.format("value for replace [%s] could not be converted to string", value)
                        );

                    for (String p : vt.getParams()) {
                        s = s.concat(p);
                    }

                    value = toJsonElement(s);
                    break;
                }

                case "prepend":
                    log.warn("transformation 'prepend' for field {} is not implemented", field.getName());
                    break;

                case "map":
                    log.warn("transformation 'map' for field {} is not implemented", field.getName());
                    break;

                case "mapBasedOn":
                    log.debug("transforming {} with mapBasedOn", field.getName());
                    value = resolveMappingValue(field, measurementCfg, root, measurementElement);
                    break;

                case "flatMap":
                    log.warn("transformation 'flatMap' for field {} is not implemented", field.getName());
                    break;

                case "substring":
                    log.warn("transformation 'substring' for field {} is not implemented", field.getName());
                    break;

                case "split":
                    log.warn("transformation 'split' for field {} is not implemented", field.getName());
                    break;

                case "combine": // TODO fuse multiple fields into one
                    throw new RuntimeException(
                            String.format(
                                    "the provided transformation type %s is not yet supported (in development)",
                                    type
                            )
                    );

                default:
                    throw new RuntimeException(
                            String.format("the provided transformation type %s is not supported", type)
                    );
            }
        }

        return value;
    }


    static String deriveRelativePath(String rawPath, String measurementPath) {
        if (rawPath == null || measurementPath == null) return null;
        if (rawPath.startsWith(measurementPath)) {
            return stripLeadingDot(rawPath.substring(measurementPath.length()));
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

    static JsonElement getByPath(JsonElement root, String path) {
        if (root == null || path == null) return null;
        List<PathToken> tokens = tokenize(path);
        JsonElement current = root;
        //iterate through the json tree via the tokens we have just created until we find the field (as a JsonElement) that we are looking for
        log.debug(tokens.toString());

        for (PathToken token : tokens) {
            if (current == null || current.isJsonNull()) return null;
            if (token instanceof FieldToken field) {
                log.debug("next field {} in path of {}", field.name, path);
                if (!current.isJsonObject()) {
                    log.debug("current field is {} and not json object but {}", current, current.getClass());
                    return null;
                }
                current = current.getAsJsonObject().get(field.name);
            } else if (token instanceof IndexToken indexToken) {
                log.error("this shouldn't happen");
                if (!current.isJsonArray()) {
                    log.debug("current field is {} and not json array but {}", current, current.getClass());
                    return null;
                }
                JsonArray arr = current.getAsJsonArray();
                if (indexToken.index < 0 || indexToken.index >= arr.size()) return null;
                current = arr.get(indexToken.index);
            }
        }
        log.debug("current is of type {} and value {}", current.getClass(), current);
        return current;
    }

    /***
     * Expands the simple path for a JsonObject in a measurement array to an indexed one
     * @param rawPath is the raw path
     * @param measurementCfg is used to derive the path to the array
     * @param measurementIndex is used to identify which measurement we are looking at
     * @return the path enriched with an index
     */
    private static String expandPathForMeasurement(String rawPath,
                                                   MeasurementPathConfig measurementCfg,
                                                   int measurementIndex) {
        if (rawPath == null || measurementCfg == null) return rawPath;
        String measurementPath = measurementCfg.getPath();
        if (measurementPath == null || measurementPath.isBlank()) return rawPath;
        if (!rawPath.startsWith(measurementPath)) {
            return rawPath;
        }
        int prefixLen = measurementPath.length();
        if (rawPath.length() > prefixLen && rawPath.charAt(prefixLen) == '[') {
            return rawPath;
        }
        return measurementPath + "[" + measurementIndex + "]" + rawPath.substring(prefixLen);
    }

    static void setAtTarget(JsonObject outgoingElementTemplate, String targetPath, JsonElement value) {
        List<PathToken> tokens = tokenize(targetPath);
        if (tokens.isEmpty()) return;
        JsonElement current = outgoingElementTemplate;
        for (int i = 0; i < tokens.size(); i++) {
            PathToken token = tokens.get(i);

            //sequentially going through the target path and building it as we go
            if (token instanceof FieldToken field) {
                JsonObject obj = current.getAsJsonObject();
                if (i == tokens.size() - 1) {
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
                    log.warn("Inserting empty field into FHIR json array, please ensure that indexes in target fields are set as intended");
                    arr.add(JsonNull.INSTANCE);
                }
                if (i == tokens.size() - 1) {
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
        StringBuilder current = new StringBuilder();
        //iterate over all chars in the sourcePath of the field
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
                //figure out the index of a token that is given with some base10 math magic
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
        //add the last field
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

    static String primitiveAsString(JsonElement element) {
        if (element == null || element.isJsonNull()) return null;
        if (element.isJsonPrimitive()) return element.getAsJsonPrimitive().getAsString();
        return element.toString();
    }

    static abstract class PathToken {
    }

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
