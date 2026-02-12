import os
from dataclasses import dataclass
from pathlib import Path
import yaml
from pydantic import ValidationError

from fhir_serde.model import FhirYamlConfig


@dataclass(frozen=True)
class Settings:
    yaml_path: str
    graphs_path: str

def get_settings() -> Settings:
    return Settings(
        yaml_path = os.environ["YAML_PATH"],
        graphs_path = os.environ["GRAPHS_PATH"]
    )

def get_env_values() -> tuple[FhirYamlConfig, str]:
    settings = get_settings()

    parsed_yaml = load_config(settings.yaml_path)

    with open(settings.graphs_path, "r") as stream:
        graphs_string = stream.read()

    return parsed_yaml, graphs_string

def load_config(path: str) -> FhirYamlConfig:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return FhirYamlConfig.model_validate(data)  # pydantic v2
    except (FileNotFoundError, yaml.YAMLError, ValidationError) as e:
        raise RuntimeError(f"Failed to load/validate YAML config from {path}: {e}") from e