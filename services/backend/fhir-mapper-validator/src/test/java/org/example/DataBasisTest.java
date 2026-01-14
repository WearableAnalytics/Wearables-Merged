//package org.example;
//
//import org.example.dependencies.DependencyGraph;
//import org.example.fhir.model.MappingYaml;
//import org.example.fhir.model.FieldConfig;
//import org.example.dependencies.DataBasis;
//import org.junit.Test;
//import org.junit.jupiter.api.DisplayName;
//
//import java.util.Map;
//import java.util.Set;
//
//public class DataBasisTest {
//
//    @Test
//    @DisplayName("Testing if the minimal basis can be calculated")
//    public void testCalculateBasis() {
//
//        //TODO potentially load a few different ones here to test behaviour
//        MappingYaml yaml = ConfigLoader.loadConfig("./config/json-to-fhir-upgrade.yaml", MappingYaml.class);
//
//        DataBasis basis = new DataBasis(yaml);
//
//        for (String s: basis.getCategories()) {
//            Map<FieldConfig, Set<FieldConfig>> map = basis.getDerivativesMap(s);
//
//            System.out.printf("Dependency map for category %s\n", s);
//            for (Map.Entry<FieldConfig, Set<FieldConfig>> e : map.entrySet()) {
//                System.out.printf("Dependencies for base %s\n", e.getKey().getName());
//
//                e.getValue().forEach(x -> System.out.printf(x.getName()+"\n"));
//            }
//        }
//
//
//    }
//}
