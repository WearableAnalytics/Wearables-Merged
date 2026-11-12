package org.example;

import org.example.dependencies.DependencyGraph;
import org.example.dependencies.Node;
import org.example.fhir.model.MappingYaml;
import org.junit.Test;
import java.util.Map;
import java.util.Set;
import static org.junit.Assert.*;

public class DependencyGraphTest {
    @Test
    public void activeMappingHasATimestampBasisForEachSupportedCategory() {
        MappingYaml yaml = ConfigLoader.loadConfig("config/mapping-2026-01-28.yaml", MappingYaml.class);
        DependencyGraph graph = new DependencyGraph(yaml);
        graph.createGraphBase();
        graph.enrichGraphWithFhir();
        Map<String, Set<Node>> bases = graph.build();
        assertEquals(Set.of("measurements.instantaneous", "measurements.cumulative", "measurements.duration"), bases.keySet());
        for (Set<Node> basis : bases.values()) {
            assertFalse(basis.isEmpty());
            assertTrue(basis.stream().anyMatch(node -> node.getField().getLineProtocol() != null
                    && "timestamp".equals(node.getField().getLineProtocol().getType())));
        }
    }
}
