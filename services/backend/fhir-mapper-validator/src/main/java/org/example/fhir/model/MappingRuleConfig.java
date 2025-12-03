package org.example.fhir.model;

import java.util.List;
import lombok.Data;

@Data
public class MappingRuleConfig {
    private String path;
    private String basedOn;
    private String valueType;
    private String append;
    private List<RuleConfig> map;
}

