package org.example.fhir;

import com.google.gson.JsonElement;
import com.google.gson.JsonPrimitive;
import org.example.JsonUtils;
import org.example.fhir.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;

public class FhirTransformer extends Transformer{

    private static final Logger log = LoggerFactory.getLogger(FhirTransformer.class);

    static JsonElement resolveFhirTransformation(
            FieldConfig field,
            MeasurementPathConfig measurementCfg,
            JsonElement value
    ) {

        log.debug("mapping FHIR field {} with initial value {} and number of transformations: {}",
                field.getName(), value, field.getTransform().size());

        try {

            for (ValueTransformation vt : field.getTransform()) {

                //shouldn't happen but additional check
                if (value == null) {
                    throw new RuntimeException(String.format("Exception occurred as value for field '%s' is null during transformation processing", field.getName()));
                }

                String type = vt.getType();

                switch (type) {

                    case "toLowerCase": {
                        value = FhirTransformer.resolveToLowerCase(vt, value);
                        break;
                    }

                    case "replace": {
                        value = FhirTransformer.resolveReplace(vt, value);
                        if (value == null) return null;
                        break;
                    }

                    case "append": {
                        value = FhirTransformer.resolveAppend(vt, value);
                        break;
                    }

                    case "prepend":
                        value = resolvePrepend(vt, value);
                        break;

                    case "map":
                        try {
                            value = FhirTransformer.resolveMap(value, field, measurementCfg);
                        }catch (IllegalArgumentException iae) {
                            throw new IllegalArgumentException(String.format("Exception occurred when trying to map FHIR field '%s' with value '%s': %s", field.getName(), value, iae.getMessage()));
                        }
                        break;

                    case "flatMap": //Don't know if this is useful, skipping it for now
                        log.warn("transformation 'flatMap' for field {} is not implemented", field.getName());
                        break;

                    case "substring":
                        value = FhirTransformer.substring(vt, value);
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

                //if the field was not set yet, we requeue it
                if (value == null) {
                    return null;
                }

            }

        } catch (IllegalArgumentException iae) {
            throw new IllegalArgumentException(String.format("Exception occurred due to invalid configuration while resolving FHIR dependencies: %s", iae.getMessage()));
        }

        return value;
    }


    static JsonElement resolveMap(
            JsonElement value,
            FieldConfig field,
            MeasurementPathConfig measurementPathConfig
    ) throws IllegalArgumentException {

        String jsonPathSource = field.getFhirSource();

        if (field.getFhirSource().isBlank()) {
            throw new IllegalArgumentException(String.format("FHIR Source is empty for field %s", field.getName()));
        }
        if (field.getTarget().isBlank()) {
            throw new IllegalArgumentException(String.format("Target is empty for field %s", field.getName()));
        }
        if (value == null) {
            return null;
        }

        List<MappingRuleConfig> fitting = measurementPathConfig.getMappings().stream()
                .filter(x -> Objects.equals(x.getFieldName(), field.getName()))
                .toList();

        if (fitting.size() != 1) {
            throw new IllegalArgumentException(String.format("Exactly one mapping must be defined for a map action, missing for field '%s' with source '%s'", field.getName(), field.getFhirSource()));
        }

        String valueString = JsonUtils.primitiveAsString(value);
        if (valueString == null) {
            throw new IllegalArgumentException(String.format("Value '%s' as found in '%s' could not be converted to string", value, jsonPathSource));
        }

        List<RuleConfig> rules = fitting.get(0).getMap().stream()
                .filter(x -> Objects.equals(x.getKey(), valueString))
                .toList();

        if (rules.size() != 1){
            throw new IllegalArgumentException(String.format("A mapping map must be a surjective function over the defined / possible domain, duplicate or no domain values for '%s'", fitting.get(0).getFieldName()));
        }

        String newValue = rules.get(0).getValue();

        return new JsonPrimitive(newValue);
    }
}
