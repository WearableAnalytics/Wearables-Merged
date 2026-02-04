package org.example;

import org.apache.kafka.streams.processor.api.Processor;
import org.apache.kafka.streams.processor.api.ProcessorContext;
import org.apache.kafka.streams.processor.api.ProcessorSupplier;
import org.apache.kafka.streams.processor.api.Record;
import org.example.fhir.Mapper;
import org.example.fhir.model.MappingYaml;

import java.util.List;

class FlatMapperMockSupplier implements ProcessorSupplier<String, String, String, String> {

    public FlatMapperMockSupplier(MappingYaml yaml){
        this.yaml = yaml;
    }

    MappingYaml yaml;

    @Override
    public Processor<String, String, String, String> get() {
        return new FlatMapperMock(yaml);
    }
}

class FlatMapperMock implements Processor<String, String, String, String> {
    private ProcessorContext<String, String> context;

    public FlatMapperMock(MappingYaml yaml){
        this.mapper = new Mapper(yaml);
    }

    Mapper mapper;

    @SuppressWarnings("unchecked")
    @Override
    public void init(ProcessorContext context) {
        this.context = context;
        System.out.println("TEST");
    }

    @Override
    public void process(Record record) {
        List<String> out = mapper.flatMapJson(record.value().toString());

        for (String v : out) {
            context.forward(record.withValue(v));
        }
    }

    @Override
    public void close() {}
}
