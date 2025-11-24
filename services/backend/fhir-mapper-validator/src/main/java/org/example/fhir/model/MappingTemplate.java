package org.example.fhir.model;

import lombok.Data;

@Data
public class MappingTemplate {
    private MetadataConfig metadata;
    private MeasurementConfig measurement;
}

