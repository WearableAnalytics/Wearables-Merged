import logging

import line_protocol_parser

from src.fhir_serde.env_client import EnvClient
from src.fhir_serde.fhir_builder import FhirParser
from src.fhir_serde.api_client import ApiClient

logger = logging.getLogger(__name__)

class VersionManager:
    def __init__(self, db_client: ApiClient, env_client: EnvClient):
        self.db_client = db_client
        self.env_client = env_client
        self.current_version = None

        self.parser: dict[str, FhirParser] = {}

    def initialize(self):

        self.current_version = self.env_client.get_current_version()

    # TODO add a validation sampling rate here too? and add documentation
    def get_serializer(self, version: str, category: str) -> FhirParser:

        parser = self.parser.get(f"{version}/{category}")
        if parser is not None:
            return self.parser[version + "/" + category]


        new_parser: FhirParser

        logger.info(f"Created new client for version {version} and category {category}")
        if self.current_version == version:
            new_parser = FhirParser(self.env_client, version, category)
        else:
            new_parser = FhirParser(self.db_client, version, category)

        self.parser[version + "/" + category] = new_parser
        new_parser.prepare_yaml_and_graph()

        if not new_parser.ready:
            raise RuntimeError("unexpectedly new parser is not ready")

        return new_parser

    def transform_to_fhir(self, line_protocol_string: str) -> str:

        lp_dict = line_protocol_parser.parse_line(line_protocol_string)

        tags: dict[str, str] = lp_dict["tags"]

        version_tag: str = tags["version"]
        category_tag: str = tags["category"]

        parser: FhirParser = self.get_serializer(version_tag, category_tag)

        cleaned_lp = remove_tags(line_protocol_string)

        print(cleaned_lp)

        return parser.build_fhir(cleaned_lp)



def remove_tags(lp_string: str) -> str:

    meas_and_tags, fields, timestamp = lp_string.partition(" ")
    if not fields:
        raise RuntimeError(f"invalid line protocol string ingested: {lp_string}")

    parts = meas_and_tags.split(",")
    measurement = parts[0]
    tag_parts = parts[1:]

    kept = []
    for t in tag_parts:
        key = t.split("=", 1)[0]
        if key not in ["version", "category"]:
            kept.append(t)

    new_meas_and_tags = measurement + ("," + ",".join(kept) if kept else "")
    return new_meas_and_tags + " " + timestamp

