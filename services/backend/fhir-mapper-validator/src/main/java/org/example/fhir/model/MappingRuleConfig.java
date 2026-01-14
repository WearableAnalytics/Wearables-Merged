package org.example.fhir.model;

import java.util.List;
import lombok.Data;

@Data
public class MappingRuleConfig {
    private String fieldName;
    private String valueType;
    private String basedOnFhir;
    private List<RuleConfig> map;
}

