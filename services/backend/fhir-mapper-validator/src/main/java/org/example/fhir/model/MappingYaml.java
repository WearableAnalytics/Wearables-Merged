package org.example.fhir.model;

import lombok.Data;

import java.util.*;

@Data
public class MappingYaml  {
    private MetadataConfig metadata;
    private MeasurementConfig measurement;

    public void validate(){
        try {
            ensureUniqueNames();
        } catch(IllegalArgumentException iae) {
            throw new IllegalArgumentException(String.format("Illegal state of YAML file: %s", iae.getMessage()));
        }
    }

    private void ensureUniqueNames() throws IllegalArgumentException{

        List<String> metadataNames = this.getMetadata().getFields()
                .stream().map(FieldConfig::getName)
                .toList();

        for (MeasurementPathConfig m :this.getMeasurement().getPaths()) {

            List<String> measurementNames = new ArrayList<>(m.getFields().stream()
                    .map(FieldConfig::getName)
                    .toList());

            measurementNames.addAll(metadataNames);

            if (measurementNames.size() != measurementNames.stream().distinct().toList().size()) {
                throw new IllegalArgumentException("There are duplicate names for the fields");
            }

        }
    }
}
