"""
Oracle Hyperion EPM Extractor — main component.

Phase 1 MVP:
  - Essbase 21C: MDX queries via REST API (port 9010, Basic Auth)
  - Hyperion Planning: data slice export via REST API (port 9000, CSS SSO)
"""

import csv
import logging

from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import MessageType, SelectElement, ValidationResult

from configuration import Configuration, RowConfiguration
from essbase_client import EssbaseClient, mdx_response_to_rows
from planning_client import PlanningClient, planning_export_to_rows


class Component(ComponentBase):

    def __init__(self):
        super().__init__()

    def run(self):
        params = Configuration(**self.configuration.parameters)

        raw_rows = self.configuration.config_data.get("config_rows", [])
        if not raw_rows:
            raise UserException("No configuration rows defined. Add at least one extraction row.")

        essbase_client = None
        planning_client = None

        for row in raw_rows:
            if row.get("is_disabled"):
                continue
            row_params = RowConfiguration(**row.get("parameters", {}))
            logging.info(f"Processing row '{row.get('id', '')}': module={row_params.module}, app={row_params.application}")

            if row_params.module == "essbase":
                if essbase_client is None:
                    essbase_client = self._build_essbase_client(params)
                self._extract_essbase(essbase_client, row_params)

            elif row_params.module == "planning":
                if planning_client is None:
                    planning_client = self._build_planning_client(params)
                self._extract_planning(planning_client, row_params)

    @sync_action("listApplications")
    def list_applications(self) -> list[SelectElement]:
        """Return all Essbase applications for UI dropdown."""
        params = Configuration(**self.configuration.parameters)
        client = self._build_essbase_client(params)
        apps = client.get_applications()
        return [SelectElement(value=app["name"], label=app.get("alias") or app["name"]) for app in apps]

    @sync_action("listDatabases")
    def list_databases(self) -> list[SelectElement] | ValidationResult:
        """Return databases for a given application. Requires 'application' in the config row parameters."""
        params = Configuration(**self.configuration.parameters)

        # application may come from the current row being edited (sent in config_data)
        rows = self.configuration.config_data.get("config_rows", [])
        application = ""
        if rows:
            application = rows[0].get("parameters", {}).get("application", "")

        if not application:
            return ValidationResult(
                "Select or enter an Application name first, then reload databases.",
                MessageType.WARNING,
            )

        client = self._build_essbase_client(params)
        databases = client.get_databases(application)
        return [SelectElement(value=db["name"], label=db.get("alias") or db["name"]) for db in databases]

    def _build_essbase_client(self, params: Configuration) -> EssbaseClient:
        host = params.get_essbase_host()
        logging.info(f"Connecting to Essbase at {host}:{params.essbase_port}")
        client = EssbaseClient(
            host=host,
            port=params.essbase_port,
            username=params.username,
            password=params.password,
            ssl_verify=params.ssl_verify,
        )
        version = client.verify_connection()
        logging.info(f"Connected to Essbase version: {version}")
        return client

    def _build_planning_client(self, params: Configuration) -> PlanningClient:
        logging.info(f"Connecting to Hyperion Planning at {params.hyperion_url}")
        return PlanningClient(
            base_url=params.hyperion_url,
            username=params.username,
            password=params.password,
            ssl_verify=params.ssl_verify,
        )

    def _extract_essbase(self, client: EssbaseClient, row: RowConfiguration) -> None:
        if not row.mdx_query:
            raise UserException(
                f"Row '{row.output_table}': 'mdx_query' is required for Essbase extraction."
            )

        logging.info(f"Executing MDX on {row.application}/{row.database} -> {row.output_table}")
        response = client.execute_mdx(row.application, row.database, row.mdx_query)

        columns, data_rows = mdx_response_to_rows(response)
        if not columns:
            logging.warning(f"MDX query returned no data for {row.application}/{row.database}.")
            return

        self._write_table(row.output_table, columns, data_rows)
        logging.info(f"Written {len(data_rows)} rows to '{row.output_table}'.")

    def _extract_planning(self, client: PlanningClient, row: RowConfiguration) -> None:
        logging.info(f"Exporting data slice from {row.application}/{row.plan_type} -> {row.output_table}")

        payload: dict = {}
        if row.mdx_query:
            payload["query"] = row.mdx_query

        response = client.export_data_slice(row.application, row.plan_type, payload)
        columns, data_rows = planning_export_to_rows(response)

        if not columns:
            logging.warning(f"Planning export returned no data for {row.application}/{row.plan_type}.")
            return

        self._write_table(row.output_table, columns, data_rows)
        logging.info(f"Written {len(data_rows)} rows to '{row.output_table}'.")

    def _write_table(self, table_name: str, columns: list[str], rows: list[dict]) -> None:
        table = self.create_out_table_definition(f"{table_name}.csv", incremental=False)
        with open(table.full_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        self.write_manifest(table)


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
