from pydantic import BaseModel, ConfigDict

# Presidio and other third-party libraries define fields like `model_name` and
# `model_to_presidio_entity_mapping`. In Pydantic v2 these are treated as
# protected namespace names unless explicitly allowed.
BaseModel.model_config = ConfigDict(protected_namespaces=())
