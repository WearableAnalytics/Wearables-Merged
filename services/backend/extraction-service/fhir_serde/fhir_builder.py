from line_protocol_parser import parse_line
from fhir_serde.model import FhirYamlConfig

class LPRecord:
    def __init__(self):
        fields: list[tuple[str, str]]
        tags: list[tuple[str, str]]
        measurement: str
        time: int

class FhirParser:
    def __init__(self, yaml_basis: FhirYamlConfig):
        self.mapping_yaml = yaml_basis

    def build_fhir(self, lp_record: str) -> str:
        lp_dict = parse_line(lp_record)

        fields = lp_dict["fields"]
        tags = lp_dict["tags"]
        measurement = lp_dict["measurement"]
        time = lp_dict["time"]


    def find_by_field_name(self, field_name: str):
        for field in self.mapping_yaml.metadata.fields:
            field.name
        #TODO





