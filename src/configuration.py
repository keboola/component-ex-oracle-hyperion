from enum import StrEnum
from urllib.parse import urlparse

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class Module(StrEnum):
    ESSBASE = "essbase"
    PLANNING = "planning"


class QueryMode(StrEnum):
    CUSTOM = "custom"
    BUILDER = "builder"


class SourceConfig(BaseModel):
    """Row-level source parameters — maps to the 'source' block in configRowSchema."""

    module: Module | None = None
    application: str = ""
    database: str = ""
    mdx_query: str = ""
    plan_type: str = ""
    query_mode: QueryMode = QueryMode.CUSTOM
    column_dimension: str = ""
    column_members: list[str] = Field(default_factory=list)
    row_dimensions: list[str] = Field(default_factory=list)


class DestinationConfig(BaseModel):
    """Row-level destination parameters — maps to the 'destination' block in configRowSchema."""

    output_table: str = ""
    incremental: bool = False
    since: str = ""
    until: str = ""


class Configuration(BaseModel):
    """Root configuration — connection settings from configSchema merged with
    source/destination row settings from configRowSchema."""

    # --- Connection (configSchema, always required) ---
    hyperion_url: str
    username: str
    password: str = Field(alias="#password")
    essbase_host: str = ""
    essbase_port: int = 9010
    use_ssl: bool = True
    ssl_verify: bool = True

    # --- Extraction (configRowSchema) ---
    source: SourceConfig = Field(default_factory=SourceConfig)
    destination: DestinationConfig = Field(default_factory=DestinationConfig)

    model_config = {"populate_by_name": True, "extra": "ignore"}

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration error: {', '.join(error_messages)}")

    def _validate_row(self) -> None:
        if self.source.module == Module.ESSBASE and not self.source.database:
            raise UserException("'database' (cube name) is required for the Essbase module.")

        if self.source.module == Module.PLANNING and not self.source.plan_type:
            raise UserException("'plan_type' is required for the Planning module.")

        if self.source.query_mode == QueryMode.BUILDER and self.source.module == Module.ESSBASE:
            if not self.source.column_dimension:
                raise UserException("'column_dimension' is required in builder mode.")
            if not self.source.row_dimensions:
                raise UserException("At least one 'row_dimensions' entry is required in builder mode.")
            if self.source.column_dimension in self.source.row_dimensions:
                raise UserException(
                    f"'column_dimension' ({self.source.column_dimension!r}) must not also appear in 'row_dimensions'."
                )

    def get_essbase_host(self) -> str:
        """Return Essbase host — falls back to Hyperion URL host if not set."""
        if self.essbase_host:
            return self.essbase_host
        return urlparse(self.hyperion_url).hostname or self.hyperion_url
