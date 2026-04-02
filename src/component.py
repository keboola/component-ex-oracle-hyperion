"""
Oracle Hyperion EPM Extractor — main component.

Phase 1 MVP:
  - Essbase 21C: MDX queries via REST API (port 9010, Basic Auth)
  - Hyperion Planning: data slice export via REST API (port 9000, CSS SSO)
"""

import csv
import logging
import re
from datetime import UTC, datetime

from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import BaseType, ColumnDefinition, SupportedDataTypes
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement
from keboola.utils.date import get_past_date, parse_datetime_interval
from keboola.utils.header_normalizer import DefaultHeaderNormalizer

from configuration import Configuration, Module, QueryMode
from essbase_client import EssbaseClient, mdx_response_to_rows
from planning_client import PlanningClient, planning_export_to_rows


class Component(ComponentBase):
    def __init__(self):
        super().__init__()
        self.params = Configuration(**self.configuration.parameters)

    def run(self):
        self.params._validate_row()
        logging.info(f"Processing: module={self.params.source.module}, app={self.params.source.application}")

        if self.params.source.module == Module.ESSBASE:
            essbase_client = self._build_essbase_client(self.params)
            version = essbase_client.verify_connection()
            logging.info(f"Connected to Essbase version: {version}")
            self._extract_essbase(essbase_client, self.params)

        elif self.params.source.module == Module.PLANNING:
            planning_client = self._build_planning_client(self.params)
            self._extract_planning(planning_client, self.params)

    @sync_action("testConnection")
    def test_connection(self) -> None:
        """Verify Essbase connectivity and surface a clear error on failure."""
        client = self._build_essbase_client(self.params)
        version = client.verify_connection()
        logging.info(f"Connection OK — Essbase version: {version}")

    @sync_action("listApplications")
    def list_applications(self) -> list[SelectElement]:
        """Return all Essbase applications for UI dropdown."""
        client = self._build_essbase_client(self.params)
        apps = client.get_applications()
        return [SelectElement(value=app["name"], label=app.get("alias") or app["name"]) for app in apps]

    def _row_params(self) -> dict:
        """Return the current row parameters for sync actions.

        The platform always merges root + row parameters into a single flat
        parameters dict before calling a sync action.
        """
        return self.configuration.parameters

    @sync_action("listDatabases")
    def list_databases(self) -> list[SelectElement]:
        """Return databases for a given application."""
        source = self._row_params().get("source", {})
        application = source.get("application", "")
        if not application:
            raise UserException("Select or enter an Application name first, then reload databases.")

        client = self._build_essbase_client(self.params)
        databases = client.get_databases(application)
        return [SelectElement(value=db["name"], label=db.get("alias") or db["name"]) for db in databases]

    @sync_action("loadTables")
    def load_tables(self) -> list[SelectElement]:
        """Return cube dimensions for the selected application/database."""
        source = self._row_params().get("source", {})
        application = source.get("application", "")
        database = source.get("database", "")

        if not application or not database:
            raise UserException("Select an Application and Database first, then reload tables.")

        client = self._build_essbase_client(self.params)
        dimensions = client.get_dimensions(application, database)
        return [SelectElement(value=d["name"], label=d.get("alias") or d["name"]) for d in dimensions]

    @sync_action("loadFields")
    def load_fields(self) -> list[SelectElement]:
        """Return members for the selected column dimension."""
        source = self._row_params().get("source", {})
        application = source.get("application", "")
        database = source.get("database", "")
        dimension = source.get("column_dimension", "")

        if not application or not database or not dimension:
            raise UserException("Select an Application, Database, and Column Dimension first, then reload fields.")

        client = self._build_essbase_client(self.params)
        members = client.get_members(application, database, dimension)
        return [SelectElement(value=m["name"], label=m.get("alias") or m["name"]) for m in members]

    def _build_essbase_client(self, params: Configuration) -> EssbaseClient:
        host = params.get_essbase_host()
        logging.info(f"Connecting to Essbase at {host}:{params.essbase_port}")
        return EssbaseClient(
            host=host,
            port=params.essbase_port,
            username=params.username,
            password=params.password,
            use_ssl=params.use_ssl,
            ssl_verify=params.ssl_verify,
        )

    def _build_planning_client(self, params: Configuration) -> PlanningClient:
        logging.info(f"Connecting to Hyperion Planning at {params.hyperion_url}")
        return PlanningClient(
            base_url=params.hyperion_url,
            username=params.username,
            password=params.password,
            ssl_verify=params.ssl_verify,
        )

    def _resolve_dates(self, row: Configuration) -> tuple[str | None, str | None]:
        """Resolve since/until to YYYY-MM-DD strings. Returns (None, None) if no dates configured."""
        dest = row.destination
        if not dest.since and not dest.until and not dest.incremental:
            return None, None

        # Determine effective since
        effective_since = dest.since
        if not effective_since and dest.incremental:
            state = self.get_state_file()
            effective_since = state.get(dest.output_table, {}).get("last_run", "")

        if effective_since:
            try:
                since_dt, until_dt = parse_datetime_interval(effective_since, dest.until or "now")
            except Exception as e:
                raise UserException(
                    f"Invalid date format in 'since' or 'until': {e}. "
                    "Use relative values like 'yesterday', '3 days ago' or absolute dates YYYY-MM-DD."
                ) from e
            since_str: str | None = since_dt.strftime("%Y-%m-%d")
        else:
            since_str = None
            until_dt = get_past_date(dest.until) if dest.until else datetime.now(UTC)

        until_str: str | None = until_dt.strftime("%Y-%m-%d")
        return since_str, until_str

    def _substitute_dates(self, query: str, since: str | None, until: str | None) -> str:
        """Replace {{since}} and {{until}} placeholders in query string."""
        result = query
        if since is not None:
            result = result.replace("{{since}}", since)
        if until is not None:
            result = result.replace("{{until}}", until)
        return result

    def _save_state(self, output_table: str, until_str: str) -> None:
        """Persist last_run date into state file, keyed by output_table."""
        state = self.get_state_file()
        state[output_table] = {"last_run": until_str}
        self.write_state_file(state)

    def _build_mdx_query(self, row: Configuration) -> str:
        """Build MDX SELECT statement from builder-mode fields."""
        src = row.source
        app_db = f"{src.application}.{src.database}"

        # COLUMNS clause
        if src.column_members:
            col_set = "{" + ",".join(f"[{src.column_dimension}].[{m}]" for m in src.column_members) + "}"
        else:
            col_set = f"{{[{src.column_dimension}].Members}}"

        # ROWS clause
        def dim_set(dim: str) -> str:
            return f"{{[{dim}].Members}}"

        if len(src.row_dimensions) == 1:
            rows_clause = dim_set(src.row_dimensions[0])
        else:
            sets = [dim_set(d) for d in src.row_dimensions]
            rows_clause = sets[0]
            for s in sets[1:]:
                rows_clause = f"CrossJoin({rows_clause},{s})"

        return f"SELECT\n  {col_set} ON COLUMNS,\n  {rows_clause} ON ROWS\nFROM [{app_db}]"

    def _extract_essbase(self, client: EssbaseClient, row: Configuration) -> None:
        src, dest = row.source, row.destination

        # Determine query
        if src.query_mode == QueryMode.BUILDER:
            mdx = self._build_mdx_query(row)
            logging.info(f"Builder mode — generated MDX:\n{mdx}")
        else:
            if not src.mdx_query:
                raise UserException(
                    f"Row '{dest.output_table}': 'mdx_query' is required for Essbase extraction in custom mode."
                )
            mdx = src.mdx_query

        # Substitute date placeholders
        since_str, until_str = self._resolve_dates(row)
        mdx = self._substitute_dates(mdx, since_str, until_str)

        logging.info(f"Executing MDX on {src.application}/{src.database} -> {dest.output_table}")
        response = client.execute_mdx(src.application, src.database, mdx)

        columns, data_rows, pk_columns = mdx_response_to_rows(response)
        if not columns:
            logging.warning(f"MDX query returned no data for {src.application}/{src.database}.")
            return

        self._write_table(dest.output_table, columns, data_rows, incremental=dest.incremental, primary_key=pk_columns)
        logging.info(f"Written {len(data_rows)} rows to '{dest.output_table}'.")

        if dest.incremental and until_str:
            self._save_state(dest.output_table, until_str)

    def _extract_planning(self, client: PlanningClient, row: Configuration) -> None:
        src, dest = row.source, row.destination
        logging.info(f"Exporting data slice from {src.application}/{src.plan_type} -> {dest.output_table}")

        payload: dict = {}
        if src.mdx_query:
            payload["query"] = src.mdx_query

        response = client.export_data_slice(src.application, src.plan_type, payload)
        columns, data_rows = planning_export_to_rows(response)

        if not columns:
            logging.warning(f"Planning export returned no data for {src.application}/{src.plan_type}.")
            return

        self._write_table(dest.output_table, columns, data_rows)
        logging.info(f"Written {len(data_rows)} rows to '{dest.output_table}'.")

    _header_normalizer = DefaultHeaderNormalizer(forbidden_sub="_")

    @staticmethod
    def _webalize_columns(
        columns: list[str], rows: list[dict], primary_key: list[str]
    ) -> tuple[list[str], list[dict], list[str]]:
        """Normalize column names to match Keboola Storage rules and resolve any duplicates.

        Uses keboola.utils DefaultHeaderNormalizer (replaces forbidden chars with '_'), then
        strips leading/trailing underscores and collapses runs — matching platform webalization.
        e.g. 'Profit %' and 'Margin %' both normalize to 'Profit' / 'Margin', colliding with
        plain members of the same name; duplicates are disambiguated with a _1, _2 … suffix.
        """
        normalizer = Component._header_normalizer
        normalized = normalizer.normalize_header(columns)
        # Strip leading/trailing underscores; collapse consecutive underscores into one.
        normalized = [re.sub(r"_+", "_", n).strip("_") or "empty" for n in normalized]

        # Resolve duplicates: second occurrence of "Profit" becomes "Profit_1", etc.
        # Track all names upfront to prevent suffix collisions (e.g. "A_1" suffix hitting an
        # existing "A_1" column).
        seen: dict[str, int] = {}
        final: list[str] = []
        occupied: set[str] = set(normalized)
        for name in normalized:
            if name not in seen:
                seen[name] = 0
                final.append(name)
            else:
                seen[name] += 1
                candidate = f"{name}_{seen[name]}"
                while candidate in occupied:
                    seen[name] += 1
                    candidate = f"{name}_{seen[name]}"
                occupied.add(candidate)
                final.append(candidate)

        # Rename keys in row dicts and primary_key list where the name changed
        rename = {old: new for old, new in zip(columns, final) if old != new}
        if rename:
            rows = [{rename.get(k, k): v for k, v in row.items()} for row in rows]
            primary_key = [rename.get(k, k) for k in primary_key]
            logging.info(
                "Normalized %d column name(s) to satisfy Storage API: %s",
                len(rename),
                rename,
            )

        return final, rows, primary_key

    def _write_table(
        self,
        table_name: str,
        columns: list[str],
        rows: list[dict],
        incremental: bool = False,
        primary_key: list[str] | None = None,
    ) -> None:
        columns, rows, primary_key = self._webalize_columns(columns, rows, primary_key or [])
        schema = self._build_schema(columns, primary_key, rows)
        table = self.create_out_table_definition(
            f"{table_name}.csv",
            incremental=incremental,
            schema=schema,
            primary_key=primary_key,
            has_header=True,
        )
        with open(table.full_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        self.write_manifest(table)

    @staticmethod
    def _build_schema(columns: list[str], primary_key: list[str], rows: list[dict]) -> dict[str, ColumnDefinition]:
        """Infer column types from the first non-empty data row.
        The Essbase API serialises numbers as JSON strings, so we attempt float() conversion."""
        pk_set = set(primary_key)
        sample = next((r for r in rows if any(r.values())), {})
        schema = {}
        for col in columns:
            val = sample.get(col)
            try:
                float(val)
                is_numeric = True
            except (TypeError, ValueError):
                is_numeric = False
            dtype = SupportedDataTypes.NUMERIC if is_numeric else SupportedDataTypes.STRING
            schema[col] = ColumnDefinition(
                data_types=BaseType(dtype=dtype),
                nullable=True,
                primary_key=col in pk_set,
            )
        return schema


if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
