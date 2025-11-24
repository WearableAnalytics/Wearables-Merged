package org.example.fhir.model;

import java.util.List;
import lombok.Data;

@Data
public class MetadataConfig {
    private List<FieldConfig> fields;
}

