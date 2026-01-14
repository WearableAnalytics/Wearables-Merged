package org.example.dependencies;

import lombok.Data;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.example.fhir.model.*;
import org.jgrapht.Graph;
import org.jgrapht.graph.DefaultEdge;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

public class DependencyGraph {

    private static final Logger log = LoggerFactory.getLogger(DependencyGraph.class);

    //Maybe this will grow as we implement more operations
    final Set<String> nonInjectiveFunctions = Set.of("toLowerCase", "substring");
    final Set<String> alwaysInjectiveFunctions = Set.of("prepend", "append", "replace");

    MappingYaml yaml;
    Map<String, Set<FieldConfig>> fieldSets;
    @Getter
    Map<String, Set<Node>> graphs;

    public DependencyGraph(MappingYaml yaml) {
        this.yaml = yaml;
        this.fieldSets = new HashMap<>();
        this.graphs = new HashMap<>();

        Set<String> intersection = new HashSet<>(nonInjectiveFunctions);
        intersection.retainAll(alwaysInjectiveFunctions);
        if (!intersection.isEmpty()) {
            throw new RuntimeException("a function is marked as always injective and never injective");
        }

    }

    /**
     * createGraphBase looks at all fields that are mapped from RAW directly and creates Node dependencies for tuples that have at least one field mapped through an injective function.
     */
    public void createGraphBase() {

        Map<String, Set<Node>> graphs = new HashMap<>();
        List<FieldConfig> metadataFields = this.yaml.getMetadata().getFields();

        this.yaml.getMeasurement().getPaths().forEach(
                x -> {
                    Set<FieldConfig> fields = new HashSet<>();
                    fields.addAll(x.getFields());
                    fields.addAll(metadataFields);
                    this.fieldSets.put(x.getPath(), fields);
                    graphs.put(x.getPath(), generateBaseSets(fields, x.getPath()));
                }
        );

        log.info("base creation done");
        for (Map.Entry<String, Set<Node>> e : graphs.entrySet()) {
            log.info("for category {}, found base nodes", e.getKey());
            e.getValue().forEach(x -> {
                log.info("    {}", x.getField().getName());
                x.getSuccessorKeys().forEach(succ -> log.info("      {}", succ));
            });
        }

        this.graphs = graphs;

    }

    public void enrichGraphWithFhir() {

        if (this.graphs.isEmpty()) {
            log.error("could not enrich graph, as there are no nodes configured, create a base first");
        }
        Map<String, Set<Node>> baseGraph = this.graphs;

        //TODO make this prettier
        //This looks at the FHIR target of all existing nodes and then adds fields (as nodes) as successors whose FHIR source is equal to the aforesaid target
        baseGraph.forEach((key, value) -> value
                .forEach(node -> {
                    log.info("Looking at base node {} for category {}", node.getField().getName(), key);
                    findSuccessorsForNode(node, fieldSets.get(key));
                }));

    }

    public void visualizeGraph(Collection<Node> nodes, Graph<String, DefaultEdge> graph) {
        nodes.forEach(x -> {
                    String nodeName = x.getField().getName();
                    if (!graph.containsVertex(nodeName)) {
                        graph.addVertex(nodeName);
                    }
                    log.info("Base node {}", nodeName);
                    x.getSuccessorKeys().forEach(succ -> {

                                if (!graph.containsVertex(succ)) {
                                    graph.addVertex(succ);
                                }
                                graph.addEdge(nodeName, succ);
                                Node node = x.getSuccessor(succ);
                                visualizeRecursive(node, graph);

                            }
                    );
                }
        );

    }

    private void visualizeRecursive(Node node, Graph<String, DefaultEdge> graph) {

        String base = node.getField().getName();

        node.getSuccessorNodes().forEach(succ -> {
                    if (!graph.containsVertex(succ.getField().getName())) {
                        graph.addVertex(succ.getField().getName());
                    }
                    graph.addEdge(base, succ.getField().getName());
                    visualizeRecursive(succ, graph);
                }
        );
    }

    private void findSuccessorsForNode(Node node, Set<FieldConfig> fields) {

        String nodeTarget = node.getField().getTarget();

        fields.stream()
                .filter(f -> f.getFhirSource() != null)
                .peek(f -> log.info("   {}", f.getName()))
                .filter(f -> f.getFhirSource().equals(nodeTarget))
                .peek(f -> log.info("       has same target"))
                .map(Node::new)
                .forEach(succ -> {
                    log.info("       added {} as successor for {}", succ.getField().getName(), node.getField().getName());
                    node.addSuccessor(succ.getField().getName(), succ);
                    findSuccessorsForNode(succ, fields); //recursion
                });

    }

    //TODO implement fhir dependencies with the special case of the combine function (once that is implemented)

    //TODO implement functionality so that explicit lpMappings are mapped regardless

    private Set<Node> generateBaseSets(Set<FieldConfig> fields, String category) {

        Map<String, Set<FieldConfig>> found = new HashMap<>();
        boolean foundAny = false;

        for (FieldConfig f : fields) {

            if (f.getRawSource() == null) {
                continue;
            }

            if (found.containsKey(f.getRawSource())) {
                //found FHIR fields that depend on the same RAW field
                found.get(f.getRawSource()).add(f);
                foundAny = true;

            } else {
                Set<FieldConfig> fieldsWithSource = new HashSet<>();
                fieldsWithSource.add(f);
                found.put(f.getRawSource(), fieldsWithSource);

                log.debug("Found new source in fields {}", f.getRawSource());
            }

        }

        found.entrySet().forEach(
                x -> {
                    log.info("Group with key {}", x.getKey());
                    x.getValue().forEach(y -> log.info("  {}", y.getName()));
                }
        );

        //If no fields have any dependencies, we create a map where each field is its own key, with empty dependency sets
        if (!foundAny) {
            log.warn("did not find any common dependencies in the base fields for category {}, compression will be less efficient", category);

            Map<FieldConfig, Set<FieldConfig>> noDepMap = new HashMap<>();

            found.values().stream()
                    .flatMap(Set::stream)
                    .forEach(x -> noDepMap.put(x, new HashSet<>()));

            return mapToNodes(new DependencyStruct(noDepMap));
        }

        return determineBaseField(found);

    }

    private Set<Node> determineBaseField(Map<String, Set<FieldConfig>> found) {

        Map<FieldConfig, Set<FieldConfig>> allInjectives = new HashMap<>();

        //TODO: I dont know if this is the best way to determine that we use the same tags when possible
        found.forEach((key, value) -> {
            FieldConfig optimalBase = value.stream()
                    .filter(y -> y.getTransformFromRaw() != null)
                    .filter(y -> y.getTransformFromRaw().stream()
                            .allMatch(transform -> isInjective(key, y, transform)))
                    .min(Comparator.comparingInt(x -> x.getName().length()))
                    .orElse(null);

            if (optimalBase != null) {
                log.info(String.valueOf(value.remove(optimalBase)));
                log.info("found an optimal base for source {}: {}", key, optimalBase.getName());
                value.forEach(x -> log.info("  {}", x.getName()));
                allInjectives.put(optimalBase, value);
            } else {
                value.forEach(
                        x -> allInjectives.put(x, new HashSet<>())
                );
            }
        });

        /*
        Here the map should only contain sources with the condition:
            1. Source has >1 dependent field
            2. At least one fields transformations are injective
         */

        return allInjectives.isEmpty() ? null : mapToNodes(new DependencyStruct(allInjectives));

    }

    private boolean isInjective(String category, FieldConfig field, ValueTransformation vt) {

        if (nonInjectiveFunctions.contains(vt.getType())) {
            return false;
        } else if (alwaysInjectiveFunctions.contains(vt.getType())) {
            return true;
        } else {
            //Function is injective in some cases

            //TODO expand this as more is added
            switch (vt.getType()) {
                case "map":
                    for (MeasurementPathConfig m : this.yaml.getMeasurement().getPaths()){
                        if (!m.getPath().equals(category)) {
                            continue;
                        }
                        if (checkMappingInjective(field, m)) return false;
                    }
                default:
                    throw new IllegalArgumentException(String.format("the mapping type '%s' does not exist", vt.getType()));
            }

        }

    }

    private boolean checkMappingInjective(FieldConfig field, MeasurementPathConfig m) {
        List<MappingRuleConfig> mappings = m.getMappings().stream()
                .filter(x -> x.getFieldName().equals(field.getName()))
                .toList();

        if (mappings.size() != 1) {
            throw new IllegalArgumentException("exactly one map must exist for each field that should be mapped");
        }

        return !checkMapBijective(mappings.get(0).getMap());
    }

    private boolean checkMapBijective(List<RuleConfig> rules) {
        Set<String> values = new HashSet<>();

        for (RuleConfig r : rules) {
            //Keys not duplicate should be checked before since then its not even a function

            if (!values.contains(r.getValue())) {
                values.add(r.getValue());
            } else {
                return false;
            }
        }

        return true;
    }

    private Set<Node> mapToNodes(DependencyStruct allInjectives) {

        Set<Node> nodes = new HashSet<>();

        for (Map.Entry<FieldConfig, Set<FieldConfig>> e : allInjectives.baseDerivativesMap.entrySet()) {

            Node baseNode = new Node(e.getKey());
            log.info("Added base node {}", baseNode.field.getName());

            e.getValue().forEach(
                    x -> {
                        boolean res = baseNode.addSuccessor(x.getName(), new Node(x));
                        if (!res) {
                            log.warn("could not add successor {} as it already exists", x.getName());
                        }
                        log.info("Added successor node {} with key {}", x, x.getName());
                    }

            );

            nodes.add(baseNode);

        }

        return nodes;

    }
}

@Data
@NoArgsConstructor
class DependencyStruct {

    DependencyStruct(Map<FieldConfig, Set<FieldConfig>> map) {
        this.baseDerivativesMap = map;
    }

    Map<FieldConfig, Set<FieldConfig>> baseDerivativesMap;
}
