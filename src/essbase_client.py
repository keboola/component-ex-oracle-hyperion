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
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

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
        return self._get(
            f"/applications/{application}/databases/{database}/dimensions/{dimension}/members"
        ).get("items", [])

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
            raise UserException(f"Essbase API error [{e.response.status_code}] on POST {path}: {e.response.text}") from e
        except requests.ConnectionError as e:
            raise UserException(f"Cannot connect to Essbase at {self.base_url}: {e}") from e


def mdx_response_to_rows(response: dict) -> tuple[list[str], list[dict]]:
    """
    Parse Essbase MDX response into (column_names, rows).

    The Essbase 21C MDX response structure:
    {
      "axis": [
        {"tuples": [[member, ...], ...], "dimensionInfo": [{"name": dim}, ...]},  # columns axis
        {"tuples": [[member, ...], ...], "dimensionInfo": [{"name": dim}, ...]}   # rows axis
      ],
      "data": {"ranges": [{"start": 0, "values": [v1, v2, ...]}]}
    }
    """
    axes = response.get("axis", [])
    data_section = response.get("data", {})
    values = []
    for r in data_section.get("ranges", []):
        values.extend(r.get("values", []))

    if not axes:
        logging.warning("MDX response contained no axis data.")
        return [], []

    # Axis 0 = columns, Axis 1 = rows (standard MDX convention)
    col_axis = axes[0] if len(axes) > 0 else {}
    row_axis = axes[1] if len(axes) > 1 else {}

    col_tuples = col_axis.get("tuples", [])
    col_dims = [d.get("name", f"col_{i}") for i, d in enumerate(col_axis.get("dimensionInfo", []))]

    row_tuples = row_axis.get("tuples", [])
    row_dims = [d.get("name", f"row_{i}") for i, d in enumerate(row_axis.get("dimensionInfo", []))]

    # Column headers: join tuple members with "/" if multi-dim
    col_headers = ["/".join(t) if isinstance(t, list) else str(t) for t in col_tuples]

    columns = row_dims + col_headers

    rows = []
    n_cols = len(col_tuples) or 1
    for row_idx, row_tuple in enumerate(row_tuples):
        row_members = list(row_tuple) if isinstance(row_tuple, list) else [row_tuple]
        row_values = values[row_idx * n_cols: (row_idx + 1) * n_cols]
        row_dict = dict(zip(row_dims, row_members))
        row_dict.update(dict(zip(col_headers, row_values)))
        rows.append(row_dict)

    return columns, rows
