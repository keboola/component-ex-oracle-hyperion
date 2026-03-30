import logging
from typing import Literal
from urllib.parse import urlparse

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class Configuration(BaseModel):
    """Component configuration — connection settings merged with row-level extraction parameters.

    The Keboola platform merges root-level (connection) and row-level parameters into a single
    flat parameters dict before calling the component. Both run actions and sync actions receive
    this merged dict.
    """

    # --- Connection (root-level, always required) ---
    hyperion_url: str
    username: str
    password: str = Field(alias="#password")
    essbase_host: str = ""
    essbase_port: int = 9010
    use_ssl: bool = True
    ssl_verify: bool = True
    debug: bool = False

    # --- Extraction (row-level, required for run actions) ---
    module: Literal["essbase", "planning"] | None = None
    application: str = ""
    database: str = ""
    mdx_query: str = ""
    plan_type: str = ""
    output_table: str = ""
    incremental: bool = False
    since: str = ""
    until: str = ""
    query_mode: Literal["custom", "builder"] = "custom"
    column_dimension: str = ""
    column_members: list[str] = Field(default_factory=list)
    row_dimensions: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "ignore"}

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration error: {', '.join(error_messages)}")

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        if self.module is not None:
            self._validate_row()

    def _validate_row(self) -> None:
        if self.module == "essbase" and not self.database:
            raise UserException("'database' (cube name) is required for the Essbase module.")

        if self.module == "planning" and not self.plan_type:
            raise UserException("'plan_type' is required for the Planning module.")

        if self.query_mode == "builder" and self.module == "essbase" and not self.column_dimension:
            raise UserException("'column_dimension' is required in builder mode.")

        if self.query_mode == "builder" and self.module == "essbase" and not self.row_dimensions:
            raise UserException("At least one 'row_dimensions' entry is required in builder mode.")

        if self.query_mode == "builder" and self.module == "essbase" and self.column_dimension in self.row_dimensions:
            raise UserException(
                f"'column_dimension' ({self.column_dimension!r}) must not also appear in 'row_dimensions'."
            )

    def get_essbase_host(self) -> str:
        """Return Essbase host — falls back to Hyperion URL host if not set."""
        if self.essbase_host:
            return self.essbase_host
        return urlparse(self.hyperion_url).hostname or self.hyperion_url
