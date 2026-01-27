package org.example.fhir;

import com.google.gson.*;
import lombok.Data;
import org.example.fhir.model.*;
import org.example.JsonUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

import static org.example.JsonUtils.*;
import static org.example.config.Environment.TEMPLATE;
import static org.example.fhir.Transformations.*;

@Data
public class Mapper {

    private static final Logger log = LoggerFactory.getLogger(Mapper.class);

    public static Map<String, MapReturn> mapFhir(String str) {
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
            return new HashMap<>();
        }

        //We return a map that maps from the category / path of the incoming JSON to all FHIR JSONs that were created using that configuration
        Map<String, MapReturn> observations = new HashMap<>();
        for (MeasurementPathConfig pathConfig : measurementCfg.getPaths()) {
            List<JsonObject> valid = new ArrayList<>();
            List<JsonObject> invalid = new ArrayList<>();
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
                    boolean res1 = applyFields(template, TEMPLATE.getMetadata(), pathConfig, incoming, measurementElement, idx);
                    boolean res2 = applyFields(template, pathConfig, incoming, measurementElement, idx);
                    if (!template.isEmpty() && res1 && res2) valid.add(template);
                    else invalid.add(template);
                }
            } else {
                throw new RuntimeException("Mapping of only a subset of measurements is not yet supported");
                //TODO implement filtering function to decide what to map instead of index based
            }
            MapReturn mr = new MapReturn(valid, invalid);
            observations.put(pathConfig.getPath(), mr);
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

    private static boolean applyFields(JsonObject target,
                                       MetadataConfig metadataCfg,
                                       MeasurementPathConfig measurementCfg,
                                       JsonObject root,
                                       JsonElement measurementElement,
                                       int idx) {
        if (metadataCfg == null || metadataCfg.getFields() == null || metadataCfg.getFields().isEmpty()) return false;
        for (FieldConfig field : metadataCfg.getFields()) {
            try{
                applySingleField(target, field, measurementCfg, root, measurementElement, idx);
            }catch (IllegalStateException ise) {
                log.warn("Found illegal state in metadata, skipping datapoint with exception: {}", ise.toString());
                return false;
            }
        }
        return true;
    }

    private static boolean applyFields(JsonObject target,
                                       MeasurementPathConfig pathConfig,
                                       JsonObject root,
                                       JsonElement measurementElement,
                                       int idx) {
        if (pathConfig == null || pathConfig.getFields() == null || pathConfig.getFields().isEmpty()) return false;
        for (FieldConfig field : pathConfig.getFields()) {
            try{
                applySingleField(target, field, pathConfig, root, measurementElement, idx);
            } catch (IllegalStateException ise) {
                log.warn("Found illegal state in measurements, skipping datapoint with exception: {}", ise.toString());
                return false;
            }
        }
        return true;
    }

    private static void applySingleField(JsonObject outgoingElementTemplate,
                                         FieldConfig field,
                                         MeasurementPathConfig measurementCfg,
                                         JsonObject rootOfIncoming,
                                         JsonElement measurementElement,
                                         int idx) throws IllegalStateException {
        if (field == null) return;
        if (field.getTarget() == null || field.getTarget().isBlank()) {
            log.warn("Skipping field '{}' because outgoingElementTemplate is missing", field.getName());
            return;
        }
        JsonElement value;
        if (field.getTransform() != null && !field.getTransform().isEmpty()) {
            //log.debug("found field that needs to be transformed: {}", field.getName());
            value = resolveTransformationField(field, measurementCfg, rootOfIncoming, measurementElement, idx);
        } else if (field.getValue() != null) {
            //log.debug("found field that needs to be retrieved from value: {}", field.getName());
            value = toJsonElement(field.getValue());
        } else {
            //log.debug("found field {} that needs to be retrieved from source: {}", field.getName(), field.getSource());
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
            //log.debug("mapping field {} with rule {}", field.getName(), type);

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
                    //log.debug("transforming {} with mapBasedOn", field.getName());
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

}
