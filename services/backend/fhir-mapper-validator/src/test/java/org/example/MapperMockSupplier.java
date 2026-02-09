package org.example;

import org.apache.kafka.streams.processor.api.Processor;
import org.apache.kafka.streams.processor.api.ProcessorContext;
import org.apache.kafka.streams.processor.api.ProcessorSupplier;
import org.apache.kafka.streams.processor.api.Record;
import org.example.config.Environment;
import org.example.dependencies.DependencyGraph;
import org.example.dependencies.Node;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.fhir.model.MappingYaml;

import java.util.Map;
import java.util.Set;

class MapperMockSupplier implements ProcessorSupplier<String, String, String, String> {

    public MapperMockSupplier(MappingYaml yaml, int validationFrq){
        this.yaml = yaml;
        this.validationFrq = validationFrq;
    }

    MappingYaml yaml;
    int validationFrq;

    @Override
    public Processor<String, String, String, String> get() {
        return new MapperMock(this.yaml, validationFrq);
    }
}

class MapperMock implements Processor<String, String, String, String> {
    private ProcessorContext<String, String> context;

    public MapperMock(MappingYaml yaml, int validationFrq){
        this.mapper = new Mapper(yaml, validationFrq);
    }

    Mapper mapper;
    Map<String, Set<Node>> categoryGraphs;

    @SuppressWarnings("unchecked")
    @Override
    public void init(ProcessorContext context) {
        Validator.initiliazeFhirValidator(mapper.getValidationFrq());
        this.context = context;

        DependencyGraph dependencyGraph = new DependencyGraph(mapper.getYaml());

        //This will build the dependency graph derived from the Mapping YAML
        dependencyGraph.createGraphBase();
        dependencyGraph.enrichGraphWithFhir();

        //the map maps from the category name (e.g., instantaneous, duration, etc.) to the minimal set of nodes needed to derive the rest of the fhir
        this.categoryGraphs = dependencyGraph.build();
    }

    @Override
    public void process(Record record) {
        String out = mapper.mapAndValidate(record.value().toString(), categoryGraphs);

        if (out == null) {
            System.out.println("ALARM");
            return;
        }

        if (!out.substring(0, 5).contains("{")){
            context.forward(record.withValue(out), "sinkProcessor");
        } else {
            context.forward(record.withValue(out), "dlqProcessor");
        }

    }

    @Override
    public void close() {}
}
