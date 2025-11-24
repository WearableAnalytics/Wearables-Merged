package org.example.fhir.model;

import java.util.List;
import lombok.Data;

@Data
public class MeasurementPathConfig {
    private String path;
    private boolean arrayMapAll;
    private List<FieldConfig> fields;
    private List<MappingRuleConfig> mappings;
}

