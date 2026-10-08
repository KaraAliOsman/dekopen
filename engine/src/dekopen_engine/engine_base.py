"""The shared strict base every engine model inherits — isolated so leaf
modules (glass composition, …) can define models without depending on the
whole ``models`` aggregate (which in turn needs their types)."""

from pydantic import BaseModel, ConfigDict


class EngineModel(BaseModel):
    """Strict shared configuration for deterministic engine values."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
