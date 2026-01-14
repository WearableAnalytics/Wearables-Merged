package org.example.fhir;

import com.google.gson.*;
import lombok.Data;
import org.example.JsonUtils;
import org.example.fhir.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.concurrent.SynchronousQueue;

import static org.example.JsonUtils.*;
import static org.example.config.Environment.TEMPLATE;
import static org.example.fhir.FhirTransformer.resolveFhirTransformation;

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
                    JsonObject outgoingMeasurementTemplate = metadataTemplate.deepCopy().getAsJsonObject();
                    boolean res1 = applyFields(outgoingMeasurementTemplate, TEMPLATE.getMetadata(), pathConfig, incoming, measurementElement, idx);
                    boolean res2 = applyFields(outgoingMeasurementTemplate, pathConfig, incoming, measurementElement, idx);
                    if (!outgoingMeasurementTemplate.isEmpty() && res1 && res2) valid.add(outgoingMeasurementTemplate);
                    else invalid.add(outgoingMeasurementTemplate);
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

    //TODO refactor this to be one method with the one below (?)
    private static boolean applyFields(JsonObject target,
                                       MetadataConfig metadataCfg,
                                       MeasurementPathConfig measurementCfg,
                                       JsonObject root,
                                       JsonElement measurementElement,
                                       int idx) {
        if (metadataCfg == null || metadataCfg.getFields() == null || metadataCfg.getFields().isEmpty()) return false;
        for (FieldConfig field : metadataCfg.getFields()) {
            try {
                applySingleFieldRaw(target, field, measurementCfg, root, idx);
            } catch (IllegalStateException ise) {
                log.warn("Found illegal state in metadata, skipping datapoint with exception: {}", ise.toString());
                return false;
            }
        }
        return true;
    }

    private static boolean applyFields(
            JsonObject outgoingMeasurementTemplate,
            MeasurementPathConfig pathConfig,
            JsonObject root,
            JsonElement measurementElement, //I have no idea what this does
            int idx
    ) {
        if (pathConfig == null || pathConfig.getFields() == null || pathConfig.getFields().isEmpty()) return false;

        Queue<FieldConfig> fhirDependentQueue = new SynchronousQueue<>();
        List<FieldConfig> nonFhirDependent = new ArrayList<>();


        for (FieldConfig field : pathConfig.getFields()) {
            if (field.getTransformFromFhir() != null && !field.getTransformFromFhir().isEmpty()) {
                fhirDependentQueue.add(field);
            } else {
                nonFhirDependent.add(field);
            }
        }

        for (FieldConfig field : nonFhirDependent) {

            if (!checkOneTypeOfTransform(field)) {
                throw new IllegalArgumentException(String.format("There may only be one type of transformation (RAW or FHIR) for field %s", field.getName()));
            }

            if (field.getTransformFromRaw() == null || field.getTransformFromRaw().isEmpty()) {
                continue;
            }

            try {
                applySingleFieldRaw(outgoingMeasurementTemplate, field, pathConfig, root, idx);
            } catch (IllegalStateException ise) {
                log.warn("Found illegal state in measurements, skipping datapoint with exception: {}", ise.toString());
                return false;
            }
        }

        pathConfig.getFields().forEach(x -> {
            List<FieldConfig> dependencyPath = new ArrayList<>();
            checkRecursiveDependency(pathConfig, x, dependencyPath);
        });


        while (fhirDependentQueue.peek() != null) {

            FieldConfig field = fhirDependentQueue.poll();

            String fhirSource = field.getFhirSource();
            String fhirTarget = field.getTarget();
            JsonElement baseValue = getByPath(outgoingMeasurementTemplate, fhirSource);

            if (baseValue == null) {
                fhirDependentQueue.add(field);
                continue;
            }

            //TODO maybe we can aggregate 'combine' fields in the value since its a json element, would make code cleaner i think with better separation

            JsonElement newValue = resolveFhirTransformation(field, pathConfig, baseValue);

            setAtTarget(outgoingMeasurementTemplate, fhirTarget, newValue);

        }

        return true;
    }

    private static void applySingleFieldRaw(
            JsonObject outgoingElementTemplate,
            FieldConfig field,
            MeasurementPathConfig measurementCfg,
            JsonObject rootOfIncoming,
            int idx) throws IllegalArgumentException {
        if (field == null) return;
        if (field.getTarget() == null || field.getTarget().isBlank()) {
            log.warn("Skipping field '{}' because outgoingElementTemplate is missing", field.getName());
            return;
        }
        JsonElement value;
        //1. We retreive either a value or a source field

        if (field.getValue() != null) {
            //log.debug("found field that needs to be retrieved from value: {}", field.getName());
            value = toJsonElement(field.getValue());
        } else {
            //log.debug("found field {} that needs to be retrieved from source: {}", field.getName(), field.getSource());
            String sourcePath = expandPathForMeasurement(field.getRawSource(), measurementCfg, idx);
            if (sourcePath == null || sourcePath.isBlank()) {
                if (!field.isOptional()) {
                    throw new IllegalArgumentException("Field '" + field.getName() + "' lacks a source/value but is required");
                }
                return;
            }
            //resolve = one field inside one measurement object in json //measurementElement = said measurement object
            //--> i think if measurementElement is null, resolved must also be null since its parent element does not exist
//            if ((resolved == null || resolved.isJsonNull()) && measurementElement != null && measurementCfg != null) {
//                String relative = deriveRelativePath(sourcePath, measurementCfg.getPath());
//                if (relative != null) {
//                    resolved = relative.isEmpty() ? measurementElement : getByPath(measurementElement, relative);
//                }
//            }
            JsonElement baseValue = getByPath(rootOfIncoming, sourcePath);

            if (baseValue == null || baseValue.isJsonNull()) {
                throw new IllegalArgumentException(String.format("Value for path '%s' is empty or null", sourcePath));
            }

            value = RawTransformer.resolveRawTransformation(field, measurementCfg, baseValue);
        }

        if (value == null || value.isJsonNull()) {
            if (!field.isOptional()) {
                throw new IllegalArgumentException(String.format("Missing value for required field '%s' with target '%s'", field.getName(), field.getTarget()));
            }
            return;
        }
        JsonUtils.setAtTarget(outgoingElementTemplate, field.getTarget(), deepCopyElement(value));
    }

    private static boolean checkRecursiveDependency(MeasurementPathConfig config, FieldConfig field, List<FieldConfig> dependencyPath) {

        dependencyPath.add(field);

        if (field.getFhirSource() == null || field.getFhirSource().isBlank()) {
            return false;
        } else if (field.getFhirSource().equals(dependencyPath.get(0).getTarget())) {
            throw new IllegalArgumentException(String.format("Illegal circular dependency detected with path: %s", dependencyPath));
        }

        List<FieldConfig> targetEqualsSource = config.getFields().stream()
                .filter(x -> Objects.equals(x.getTarget(), field.getFhirSource()))
                .toList();

        if (targetEqualsSource.size() > 1) {
            throw new IllegalArgumentException(String.format("Each target may only be specified once, this should have been checked during verification. Duplicate target: %s", targetEqualsSource.get(0).getTarget()));
        } else if (targetEqualsSource.isEmpty()) {
            throw new IllegalArgumentException(String.format("Specified source is not target of any field: %s", field.getFhirSource()));
        }

        FieldConfig dependentField = targetEqualsSource.get(0);

        return checkRecursiveDependency(config, dependentField, dependencyPath);
    }

    private static boolean checkOneTypeOfTransform(FieldConfig f) {

        boolean ensureOneNull = f.getTransformFromFhir() == null || f.getTransformFromRaw() == null;
        if (!ensureOneNull) {
            return f.getTransformFromFhir().isEmpty() || f.getTransformFromRaw().isEmpty();
        }

        return true;
    }

}
