package org.example.dependencies;


import lombok.Getter;
import lombok.Setter;
import org.example.fhir.model.FieldConfig;

import java.lang.reflect.Field;
import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;


public class Node {

    @Getter
    @Setter
    FieldConfig field;
    Map<String, Node> successors;
    Map<String, Node> predecessors;

    public Node(FieldConfig field){
        this.field = field;
        this.successors = new HashMap<>();
        this.predecessors = new HashMap<>();
    }

    public boolean addSuccessor(String s, Node n){
        Node node = this.successors.get(s);
        if (node != null) {
            return false;
        }
        this.successors.put(s, n);
        return true;
    }

    public Node removeSuccessor(String s) {
        Node node = this.successors.get(s);
        this.successors.remove(s);

        return node;
    }

    public boolean addPredecessor(String s, Node n) {
        Node node = this.predecessors.get(s);
        if (node != null){
            return false;
        }
        this.predecessors.put(s, n);
        return true;
    }

    public Node removePredecessor(String s) {
        Node node = this.predecessors.get(s);
        this.predecessors.remove(s);

        return node;
    }

    public Node getSuccessor(String s) {
        return this.successors.get(s);
    }

    public Node getPredecessor(String s) {
        return this.predecessors.get(s);
    }

    public Set<String> getSuccessorKeys(){
        return this.successors.keySet();
    }
    public Collection<Node> getSuccessorNodes() { return this.successors.values();}

    public Set<String> getPredecessorKeys(){
        return this.predecessors.keySet();
    }
}
