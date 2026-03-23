import logging

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class Configuration(BaseModel):
    """Root-level component configuration — authentication and server settings."""

    hyperion_url: str
    username: str
    password: str = Field(alias="#password")
    essbase_host: str = ""
    essbase_port: int = 9010
    ssl_verify: bool = True
    debug: bool = False

    model_config = {"populate_by_name": True}

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration error: {', '.join(error_messages)}")

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

    def get_essbase_host(self) -> str:
        """Return Essbase host — falls back to Hyperion URL host if not set."""
        if self.essbase_host:
            return self.essbase_host
        from urllib.parse import urlparse

        return urlparse(self.hyperion_url).hostname or self.hyperion_url


class RowConfiguration(BaseModel):
    """Row-level configuration — one row per extraction query."""

    module: str  # "essbase" or "planning"
    application: str
    database: str = ""  # Essbase cube name
    mdx_query: str = ""  # MDX SELECT statement for Essbase
    plan_type: str = ""  # Planning plan type for data export
    output_table: str

    model_config = {"populate_by_name": True}

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Row configuration error: {', '.join(error_messages)}")

        if self.module not in ("essbase", "planning"):
            raise UserException(f"Invalid module '{self.module}'. Must be 'essbase' or 'planning'.")

        if self.module == "essbase" and not self.database:
            raise UserException("'database' (cube name) is required for the Essbase module.")

        if self.module == "planning" and not self.plan_type:
            raise UserException("'plan_type' is required for the Planning module.")
