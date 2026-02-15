from src.app.db_lord_api import DbLordApi
from src.environment.settings import get_env_values, Settings
from src.fhir_serde import FhirParser


class VersionManager:
    def __init__(self, settings: Settings, client: DbLordApi):
        self.client = client

        fhir_yaml, _ = get_env_values(settings)
        self.current_version = fhir_yaml.version
        self.parser: dict[str, FhirParser] = {}
        self.settings = settings

    #TODO add a validation sampling rate here too? and add documentation
    def get_serializer(self, version: str, category: str) -> FhirParser:

        if self.parser[version+"/"+category] is None:

            is_current_version = self.current_version == version

            new_parser = FhirParser(self.client, self.settings, version, category, is_current_version)
            self.parser[version + "/" + category] = new_parser

            new_parser.prepare_yaml_and_graph()

            if not new_parser.ready:
                raise RuntimeError("unexpectedly new parser is not ready")

            return new_parser

        return self.parser[version+"/"+category]
