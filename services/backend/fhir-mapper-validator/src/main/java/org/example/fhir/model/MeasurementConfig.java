package org.example.fhir.model;

import java.util.List;
import lombok.Data;

@Data
public class MeasurementConfig {
    private List<MeasurementPathConfig> paths;
}

