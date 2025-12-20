package org.example;

import com.google.gson.*;
import org.example.fhir.Mapper;
import org.example.fhir.model.MeasurementPathConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;

public class JsonUtils {

    private static final Logger log = LoggerFactory.getLogger(JsonUtils.class);

    public static JsonElement getByPath(JsonElement root, String path) {
        if (root == null || path == null) return null;
        List<PathToken> tokens = tokenize(path);
        JsonElement current = root;
        //iterate through the json tree via the tokens we have just created until we find the field (as a JsonElement) that we are looking for
        //log.debug(tokens.toString());

        for (PathToken token : tokens) {
            if (current == null || current.isJsonNull()) return null;
            if (token instanceof FieldToken field) {
                //log.debug("next field {} in path of {}", field.name, path);
                if (!current.isJsonObject()) {
                    //log.debug("current field is {} and not json object but {}", current, current.getClass());
                    return null;
                }
                current = current.getAsJsonObject().get(field.name);
            } else if (token instanceof IndexToken indexToken) {
                if (!current.isJsonArray()) {
                    //log.debug("current field is {} and not json array but {}", current, current.getClass());
                    return null;
                }
                JsonArray arr = current.getAsJsonArray();
                if (indexToken.index < 0 || indexToken.index >= arr.size()) return null;
                current = arr.get(indexToken.index);
            }
        }
        return current;
    }

    public static List<PathToken> tokenize(String path) {
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

    public static void setAtTarget(JsonObject outgoingElementTemplate, String targetPath, JsonElement value) {
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
                    log.debug("Inserting empty field into FHIR json array, please ensure that indexes in target fields are set as intended");
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

    /***
     * Expands the simple path for a JsonObject in a measurement array to an indexed one
     * @param rawPath is the raw path
     * @param measurementCfg is used to derive the path to the array
     * @param measurementIndex is used to identify which measurement we are looking at
     * @return the path enriched with an index
     */
    public static String expandPathForMeasurement(String rawPath,
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

    public static String deriveRelativePath(String rawPath, String measurementPath) {
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

    public static JsonElement deepCopyElement(JsonElement in) {
        if (in == null) return JsonNull.INSTANCE;
        try {
            return JsonParser.parseString(in.toString());
        } catch (Exception e) {
            return in;
        }
    }

    public static JsonElement toJsonElement(Object value) {
        if (value == null) return JsonNull.INSTANCE;
        if (value instanceof JsonElement jsonElement) return jsonElement;
        if (value instanceof String string) return new JsonPrimitive(string);
        if (value instanceof Number number) return new JsonPrimitive(number);
        if (value instanceof Boolean bool) return new JsonPrimitive(bool);
        return new Gson().toJsonTree(value);
    }

    public static String primitiveAsString(JsonElement element) {
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
