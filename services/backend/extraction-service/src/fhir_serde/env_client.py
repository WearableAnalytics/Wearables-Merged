import os
import yaml

from src.app.settings import Settings
from src.fhir_serde.dot_parser import Graph, parse_graph
from src.fhir_serde.yaml_parser import parse_yaml, FieldDef, MappingDef, FhirYamlConfig

class EnvClient:
    def __init__(self, settings: Settings):
        self.settings: Settings = settings
        self.current_version = None

    def get_current_version(self) -> str:

        if self.current_version is not None:
            return self.current_version

        with open(self.settings.yaml_path, "r") as stream:
            yaml_string = stream.read()

        data = yaml.safe_load(yaml_string)
        fhir_yaml = FhirYamlConfig.model_validate(data)

        self.current_version = fhir_yaml.version

        return fhir_yaml.version


    def read_yaml_for_version_and_category(self, _: str, category: str) -> tuple[dict[str, FieldDef], dict[str, MappingDef]]:

        with open(self.settings.yaml_path, "r") as stream:
            yaml_string = stream.read()

        return parse_yaml(yaml_string, category)

    def read_graph_for_version_and_category(self, _: str, category: str) -> Graph :

        with open(self.settings.graphs_path, "r") as stream:
            graphs_string = stream.read()

        graph_list = graphs_string.split("&")

        for g in graph_list:
            if len(g) == 0:
                continue
            name = get_category_name(g)

            if name == category:
                return parse_graph(g, category)

        raise RuntimeError(f"no category matching '{category}' was found")


def get_settings() -> Settings:
    return Settings(
        yaml_path = os.environ["YAML_PATH"],
        graphs_path = os.environ["GRAPHS_PATH"]
    )

def get_category_name(g: str) -> str | None:
    lines = g.splitlines()
    for line in lines:
        if line.find("#") != -1:
            return line.removeprefix("#")

    return None
