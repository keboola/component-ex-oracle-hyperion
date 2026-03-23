import logging
from typing import Any

import requests
from keboola.component.exceptions import UserException


class EssbaseClient:
    """Client for Essbase 21C REST API (port 9010, Basic Auth)."""

    def __init__(self, host: str, port: int, username: str, password: str, ssl_verify: bool = True):
        scheme = "https" if ssl_verify else "http"
        self.base_url = f"{scheme}://{host}:{port}/essbase/rest/v1"
        self.ssl_verify = ssl_verify
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Content-Type": "application/json"})

    def verify_connection(self) -> str:
        """Return Essbase version string — use to verify connectivity."""
        data = self._get("/about")
        return data.get("version", "unknown")

    def get_applications(self) -> list[dict]:
        return self._get("/applications").get("items", [])

    def get_databases(self, application: str) -> list[dict]:
        return self._get(f"/applications/{application}/databases").get("items", [])

    def execute_mdx(self, application: str, database: str, mdx: str) -> dict:
        """Execute an MDX query and return the raw grid response."""
        payload = {"query": mdx}
        return self._post(f"/applications/{application}/databases/{database}/mdx", payload)

    def get_dimensions(self, application: str, database: str) -> list[dict]:
        return self._get(f"/applications/{application}/databases/{database}/dimensions").get("items", [])

    def get_members(self, application: str, database: str, dimension: str) -> list[dict]:
        return self._get(f"/applications/{application}/databases/{database}/dimensions/{dimension}/members").get(
            "items", []
        )

    def get_substitution_variables(self, application: str, database: str) -> list[dict]:
        return self._get(f"/applications/{application}/databases/{database}/variables").get("items", [])

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, verify=self.ssl_verify, timeout=300)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            raise UserException(f"Essbase API error [{e.response.status_code}] on GET {path}: {e.response.text}") from e
        except requests.ConnectionError as e:
            raise UserException(f"Cannot connect to Essbase at {self.base_url}: {e}") from e

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.post(url, json=payload, verify=self.ssl_verify, timeout=300)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            raise UserException(
                f"Essbase API error [{e.response.status_code}] on POST {path}: {e.response.text}"
            ) from e
        except requests.ConnectionError as e:
            raise UserException(f"Cannot connect to Essbase at {self.base_url}: {e}") from e


def mdx_response_to_rows(response: dict) -> tuple[list[str], list[dict]]:
    """
    Parse Essbase MDX response into (column_names, rows).

    Actual Essbase 21C MDX response structure:
    {
      "metadata": {"page": [...], "column": ["Year"], "row": ["Product"]},
      "data": [
        ["", "Jan", "Feb", "Mar"],      # header row: first cell empty, rest are column members
        ["Cola",  1710.0, 1666.0, ...], # data rows: first cell is row member, rest are values
        ...
      ]
    }
    """
    metadata = response.get("metadata", {})
    data = response.get("data", [])

    if not data:
        logging.warning("MDX response contained no data.")
        return [], []

    row_dims = metadata.get("row", ["row"])
    col_members = data[0][1:]  # first row, skip leading empty cell

    # Build column names: row dimension name(s) + column member names
    columns = row_dims + [str(c) for c in col_members]

    n_row_dims = len(row_dims)
    rows = []
    for raw_row in data[1:]:
        if not raw_row:
            continue
        row_members = raw_row[:n_row_dims]
        values = raw_row[n_row_dims:]
        row_dict = dict(zip(row_dims, row_members))
        row_dict.update({str(col): val for col, val in zip(col_members, values)})
        rows.append(row_dict)

    return columns, rows
