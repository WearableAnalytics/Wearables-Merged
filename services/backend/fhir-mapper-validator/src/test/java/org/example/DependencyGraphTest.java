package org.example;

import org.example.dependencies.DependencyGraph;
import org.example.dependencies.Node;
import org.example.fhir.model.MappingYaml;
import org.jgrapht.Graph;
import org.jgrapht.graph.DefaultDirectedGraph;
import org.jgrapht.graph.DefaultEdge;
import org.jgrapht.nio.dot.DOTExporter;
import org.junit.Test;
import org.junit.jupiter.api.DisplayName;

import java.io.FileWriter;
import java.io.IOException;
import java.util.Map;
import java.util.Set;

public class DependencyGraphTest {

    @Test
    @DisplayName("Testing if the minimal basis can be calculated")
    public void testCalculateBasis() {

        //TODO potentially load a few different ones here to test behaviour
        MappingYaml yaml = ConfigLoader.loadConfig("./config/json-to-fhir-dependenciesExample.yaml", MappingYaml.class);

        DependencyGraph g = new DependencyGraph(yaml);

        g.createGraphBase();
        g.enrichGraphWithFhir();


        //Visualize the graphs

        g.getGraphs().entrySet().forEach(
                x -> {
                    Graph<String, DefaultEdge> graph = new DefaultDirectedGraph<>(DefaultEdge.class);

                    g.visualizeGraph(x.getValue(), graph);

                    DOTExporter<String, DefaultEdge> exporter = new DOTExporter<>(v -> v);

                    String key = x.getKey().replace(".", "_");
                    try {
                        System.out.println(key);
                        exporter.exportGraph(graph, new FileWriter(String.format("dependencyGraph_%s.dot", key)));
                    } catch (IOException e) {
                        throw new RuntimeException(e);
                    }

                    System.out.printf("Graph exported as dependencyGraph_%s.dot\n", key);

                }
        );
    }

}
