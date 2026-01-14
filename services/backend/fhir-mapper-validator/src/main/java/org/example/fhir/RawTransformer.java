package org.example.fhir;

import com.google.gson.JsonElement;
import org.example.fhir.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;

import static org.example.JsonUtils.*;

public class RawTransformer extends Transformer{

    private static final Logger log = LoggerFactory.getLogger(RawTransformer.class);

    static JsonElement resolveRawTransformation(
            FieldConfig field,
            MeasurementPathConfig measurementCfg,
            JsonElement value
    ) {
        log.debug(
                "retrieved source for field {}: {}; it has {} number of mappings",
                field.getName(), field.getRawSource(), field.getTransformFromRaw().size()
        );

        // apply transformations in the order they were listed
        for (ValueTransformation vt : field.getTransformFromRaw()) {

            String type = vt.getType();
            //log.debug("mapping field {} with rule {}", field.getName(), type);

            switch (type) {

                case "toLowerCase": {
                    value = RawTransformer.resolveToLowerCase(vt, value);
                    break;
                }

                case "replace": {
                    value = RawTransformer.resolveReplace(vt, value);
                    if (value == null) return null;
                    break;
                }

                case "append": {
                    value = RawTransformer.resolveAppend(vt, value);
                    break;
                }

                case "prepend":
                    log.warn("transformation 'prepend' for field {} is not implemented", field.getName());
                    break;

                case "map": //TODO rename this everywhere
                    //log.debug("transforming {} with mapBasedOn", field.getName());
                    try {
                        value = RawTransformer.resolveMap(value, field, measurementCfg);
                    }catch (IllegalArgumentException iae) {
                        throw new IllegalArgumentException(String.format("Exception occurred when trying to map RAW field '%s' with value '%s': %s", field.getName(), value, iae.getMessage()));
                    }
                    break;

                case "flatMap": //Don't know if this is useful, skipping it for now
                    log.warn("transformation 'flatMap' for field {} is not implemented", field.getName());
                    break;

                case "substring":
                    value = RawTransformer.substring(vt, value);
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

    static JsonElement resolveMap(
            JsonElement value,
            FieldConfig field,
            MeasurementPathConfig measurementCfg
    ) throws IllegalArgumentException {
        if (measurementCfg == null || measurementCfg.getMappings() == null || measurementCfg.getMappings().isEmpty()) {
            throw new IllegalArgumentException("There are no mappings configured");
        }

        MappingRuleConfig ruleConfig = findApplicableMap(field, measurementCfg);
        if (ruleConfig == null) return null;

//        if ((basedOnValue == null || basedOnValue.isJsonNull()) && measurementElement != null) {
//            String relative = deriveRelativePath(basedOnPath, measurementCfg.getPath());
//            if (relative != null) {
//                basedOnValue = relative.isEmpty() ? measurementElement : getByPath(measurementElement, relative);
//            }
//        }
        String key = primitiveAsString(value);
        if (key == null) {
            throw new IllegalArgumentException("Could not map since value of field could not be converted to string-key");
        }

        List<RuleConfig> rules = ruleConfig.getMap();
        if (rules == null || rules.isEmpty()) {
            throw new IllegalArgumentException("Mapping rule for has no map entries");
        }

        for (RuleConfig rule : rules) {
            if (rule != null && Objects.equals(rule.getKey(), key)) {
                return toJsonElement(rule.getValue());
            }
        }

        throw new IllegalArgumentException("Map for field did not contain any keys");
    }

    private static MappingRuleConfig findApplicableMap(FieldConfig field, MeasurementPathConfig measurementCfg) {
        MappingRuleConfig ruleConfig = measurementCfg.getMappings().stream()
                .filter(rule -> rule != null && Objects.equals(rule.getFieldName(), field.getName()))
                .findFirst()
                .orElse(null);
        if (ruleConfig == null) {
            log.warn("No mapping rule found for target '{}'", field.getTarget());
            return null;
        }
        return ruleConfig;
    }

    static String elementToString(JsonElement je) {
        String valueAsString = null;
        try {
            valueAsString = je.getAsString();
        } catch (IllegalStateException ise) {
            throw new RuntimeException("toLowerCase can only be called on fields that can be cast to string, but was a JsonObject, JsonArray or null");
        }
        return valueAsString;
    }
}
