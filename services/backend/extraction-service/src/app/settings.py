from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    db_lord_base_url: str = "http://db-lord:8000"
    yaml_path: str = "/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example.yaml"
    graphs_path: str = "/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example_dot.txt"



settings = Settings()
