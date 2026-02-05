package org.example.dependencies;

import lombok.Data;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.example.config.Environment;
import org.example.fhir.model.*;
import org.jgrapht.Graph;
import org.jgrapht.graph.DefaultEdge;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.stream.Collectors;

public class DependencyGraph {

    private static final Logger log = LoggerFactory.getLogger(DependencyGraph.class);

    //Maybe this will grow as we implement more operations
    final Set<String> nonInjectiveFunctions = Set.of("toLowerCase", "substring");
    final Set<String> alwaysInjectiveFunctions = Set.of("prepend", "append", "replace");

    MappingYaml yaml;
    Map<String, Set<FieldConfig>> fieldSets;
    private Map<String, Set<Node>> graphs;

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

        log.debug("base creation done");
        for (Map.Entry<String, Set<Node>> e : graphs.entrySet()) {
            log.debug("for category {}, found base nodes", e.getKey());
            e.getValue().forEach(x -> {
                log.debug("    {}", x.getField().getName());
                x.getSuccessorKeys().forEach(succ -> log.debug("      {}", succ));
            });
        }

        this.graphs = graphs;

    }

    public void enrichGraphWithFhir() {

        if (this.graphs.isEmpty()) {
            log.error("could not enrich graph, as there are no nodes configured, create a base first");
        }
        Map<String, Set<Node>> baseGraph = this.graphs;

        //This looks at the FHIR target of all existing nodes and then adds fields (as nodes) as successors whose FHIR source is equal to the aforesaid target
        baseGraph.forEach((key, value) -> value
                .forEach(node -> {
                    log.debug("Looking at base node {} for category {}", node.getField().getName(), key);
                    findSuccessorsForNode(node, fieldSets.get(key));
                }));

    }

    /**
     * `build()` adds all mandatory nodes to the baseNodes as specified in the schema and should be the only point where the graphs are exposed, so that the actions this method performs are mandatory
     * @return graphs for all categories
     */
    public Map<String, Set<Node>> build(){

        log.info("Starting graph creation");

        for (MeasurementPathConfig m : this.yaml.getMeasurement().getPaths()) {

            Set<Node> matchingGraph = graphs.get(m.getPath());

            Set<FieldConfig> currentBaseFields = matchingGraph.stream()
                    .map(Node::getField)
                    .collect(Collectors.toSet());

            Set<FieldConfig> mandatoryFields = m.getFields().stream()
                    .filter(x -> x.getLineProtocol().isMandatory())
                    .collect(Collectors.toSet());

            log.debug("Found node set");
            matchingGraph.forEach(x -> log.debug("   {}", x.getField().getName()));

            for (FieldConfig f : mandatoryFields) {

                FieldConfig anyMatch = currentBaseFields.stream()
                        .filter(x -> x.getName().equals(f.getName()))
                        .findAny()
                        .orElse(null);

                if (anyMatch == null) {
                    //When a mandatory node is not contained in the base set, we add it
                    this.graphs.get(m.getPath()).add(new Node(f));
                }

            }

            try{
                checkLineProtocolIntegrity(m.getPath());
            } catch (IllegalArgumentException iae) {
                throw new IllegalArgumentException(String.format("the nodes in the baseSet form cannot form valid LineProtocol: %s", iae.getMessage()));
            }
        }

        log.info("Graph creation completed");

        return graphs;

    }

    private void checkLineProtocolIntegrity(String measurementPath) {
        //these mandatory fields must contain the measurement and the timestamp
        Set<Node> graph = this.graphs.get(measurementPath);

        boolean hasMeasurement = graph.stream().anyMatch(x -> x.getField().getLineProtocol().getType().equals("measurement"));
        boolean hasTimestamp = graph.stream().anyMatch(x -> x.getField().getLineProtocol().getType().equals("timestamp"));

        if (!hasMeasurement || !hasTimestamp) {
            throw new IllegalArgumentException("the minimal base of fields must contain exactly one field marked as 'timestamp' and 'measurement' respectively");
        }

        //all base fields must have a LineProtocol specification, and one of them must be a field
        boolean hasValue = this.graphs.get(measurementPath).stream()
                .filter(x -> x.getField().getLineProtocol() != null)
                .anyMatch(x -> x.getField().getLineProtocol().getType().equals("field"));

        if (!hasValue) {
            throw new IllegalArgumentException("the minimal base of fields must contain at least one field marked as 'field'");
        }
    }

    public void visualizeGraph(Collection<Node> nodes, Graph<String, DefaultEdge> graph) {
        nodes.forEach(x -> {
                    String nodeName = x.getField().getName();
                    if (!graph.containsVertex(nodeName)) {
                        graph.addVertex(nodeName);
                    }
                    log.debug("Base node {}", nodeName);
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
                .peek(f -> log.debug("   {}", f.getName()))
                .filter(f -> f.getFhirSource().equals(nodeTarget))
                .peek(f -> log.debug("       has same target"))
                .map(Node::new)
                .forEach(succ -> {
                    log.debug("       added {} as successor for {}", succ.getField().getName(), node.getField().getName());
                    if (checkRecursiveDep(succ, node)) {
                        throw new IllegalArgumentException(String.format("there is an illegal circular dependency in the fields with nodes (%s, %s) please check your configuration", succ.getField().getName(), node.getField().getName()));
                    }
                    boolean success = connectNodes(node, succ);
                    if (!success) {
                        log.warn("  could not connect nodes ({}, {}) as they are already connected", node.getField().getName(), succ.getField().getName());
                    }
                    findSuccessorsForNode(succ, fields); //recursion
                });

    }

    private boolean checkRecursiveDep(Node succ, Node current){

        if (current.getField().getFhirSource() == null) {
            //I think this means we have found a field at the base of the dependency tree
            log.debug("found one bottom of dependencies: {}", current.getField().getName());
            return false;
        }else if (current.getField().getFhirSource().equals(succ.getField().getTarget())) {
            //We have a circular dependency with the current node
            return true;
        }

        //We don't have a circular dependency with the current node, so we check with the next one until there are no more nodes left in the graph

        for (String s : current.getPredecessorKeys()) {
            Node n = current.getPredecessor(s);
            checkRecursiveDep(succ, n);
        }

        return false;

    }
    //TODO implement fhir dependencies with the special case of the combine function (once that is implemented)

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
                    log.debug("Group with key {}", x.getKey());
                    x.getValue().forEach(y -> log.debug("  {}", y.getName()));
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
                    .filter(y -> y.getTransform() != null)
                    .filter(y -> y.getTransform().stream()
                            .allMatch(transform -> isInjective(key, y, transform)))
                    .min(Comparator.comparingInt(x -> x.getName().length()))
                    .orElse(null);

            if (optimalBase != null) {
                log.debug(String.valueOf(value.remove(optimalBase)));
                log.debug("found an optimal base for source {}: {}", key, optimalBase.getName());
                value.forEach(x -> log.debug("  {}", x.getName()));
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
                    return true;
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
            log.debug("Added base node {}", baseNode.field.getName());

            e.getValue().forEach(
                    x -> {
                        Node newNode = new Node(x);
                        boolean success = connectNodes(baseNode, newNode);
                        if (!success) {
                            log.warn("  could not connect nodes in base set({}, {}) as they are already connected", baseNode.getField().getName(), newNode.getField().getName());
                        }
                        log.debug("  Added successor node {} with key {}", x, x.getName());
                    }

            );

            nodes.add(baseNode);

        }

        return nodes;

    }

    private boolean connectNodes(Node base, Node succ){

        boolean successSuccessor = base.addSuccessor(succ.getField().getName(), succ);
        boolean successPredecessor = succ.addPredecessor(base.getField().getName(), base);

        if (successPredecessor && successSuccessor) {
            return true;
        } else if (!(successPredecessor || successSuccessor)) {
            return false;
        } else {
            throw new RuntimeException(String.format("nodes (%s, %s) were not connected correctly", base.getField().getName(), succ.getField().getName()));
        }

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
