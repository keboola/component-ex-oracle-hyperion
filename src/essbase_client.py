import json
import logging
import time
from typing import Any

import requests
from keboola.component.exceptions import UserException

# Essbase error codes that indicate a transient server-side timeout worth retrying
_RETRYABLE_ESSBASE_CODES = {1042017}
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_BASE = 5  # seconds; delay = base * 2^attempt


class EssbaseClient:
    """Client for Essbase 21C REST API (port 9010, Basic Auth)."""

    def __init__(
        self, host: str, port: int, username: str, password: str, use_ssl: bool = True, ssl_verify: bool = True
    ):
        scheme = "https" if use_ssl else "http"
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

    def get_dimensions(self, application: str, database: str) -> list[dict]:
        """Lists cube dimensions."""
        return self._get(f"/applications/{application}/databases/{database}/dimensions").get("items", [])

    def get_members(self, application: str, database: str, dimension: str) -> list[dict]:
        """Lists members for a dimension via MDX query (the REST API has no direct members endpoint)."""
        mdx = f"SELECT {{[{dimension}].Members}} ON COLUMNS FROM [{application}.{database}]"
        response = self.execute_mdx(application, database, mdx)
        data = response.get("data", [])
        if not data:
            return []
        # data[0] is the header row: first cell is empty/dimension label, rest are member names
        members = [{"name": str(m)} for m in data[0][1:]]
        return members

    def execute_mdx(self, application: str, database: str, mdx: str) -> dict:
        """Execute an MDX query and return the raw grid response."""
        payload = {"query": mdx}
        return self._post(f"/applications/{application}/databases/{database}/mdx", payload)

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = self.session.get(url, verify=self.ssl_verify, timeout=300)
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                if self._is_retryable(e) and attempt < _RETRY_ATTEMPTS - 1:
                    delay = _RETRY_BACKOFF_BASE * (2**attempt)
                    logging.warning(
                        "Essbase timeout on GET %s (attempt %d/%d), retrying in %ds…",
                        path,
                        attempt + 1,
                        _RETRY_ATTEMPTS,
                        delay,
                    )
                    time.sleep(delay)
                    last_exc = e
                    continue
                raise UserException(
                    f"Essbase API error [{e.response.status_code}] on GET {path}: {e.response.text}"
                ) from e
            except requests.ConnectionError as e:
                raise UserException(f"Cannot connect to Essbase at {self.base_url}: {e}") from e
        raise UserException(f"Essbase GET {path} failed after {_RETRY_ATTEMPTS} attempts") from last_exc

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = self.session.post(url, json=payload, verify=self.ssl_verify, timeout=300)
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                if self._is_retryable(e) and attempt < _RETRY_ATTEMPTS - 1:
                    delay = _RETRY_BACKOFF_BASE * (2**attempt)
                    logging.warning(
                        "Essbase timeout on POST %s (attempt %d/%d), retrying in %ds…",
                        path,
                        attempt + 1,
                        _RETRY_ATTEMPTS,
                        delay,
                    )
                    time.sleep(delay)
                    last_exc = e
                    continue
                raise UserException(
                    f"Essbase API error [{e.response.status_code}] on POST {path}: {e.response.text}"
                ) from e
            except requests.ConnectionError as e:
                raise UserException(f"Cannot connect to Essbase at {self.base_url}: {e}") from e
        raise UserException(f"Essbase POST {path} failed after {_RETRY_ATTEMPTS} attempts") from last_exc

    @staticmethod
    def _is_retryable(e: requests.HTTPError) -> bool:
        """Return True if the Essbase error code indicates a transient timeout."""
        try:
            body = json.loads(e.response.text)
            return body.get("errorCode") in _RETRYABLE_ESSBASE_CODES
        except (ValueError, AttributeError):
            return False


def mdx_response_to_rows(response: dict) -> tuple[list[str], list[dict], list[str]]:
    """
    Parse Essbase MDX response into (column_names, rows, primary_key_columns).

    primary_key_columns are the row dimension column names — they uniquely identify each row.

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
        return [], [], []

    row_dims = metadata.get("row", ["row"])
    n_row_dims = len(row_dims)
    col_members = data[0][n_row_dims:]  # first row, skip one leading empty cell per row dimension

    # Build column names: row dimension name(s) + column member names
    columns = row_dims + [str(c) for c in col_members]

    rows = []
    for raw_row in data[1:]:
        if not raw_row:
            continue
        row_members = raw_row[:n_row_dims]
        values = raw_row[n_row_dims:]
        row_dict = dict(zip(row_dims, row_members))
        row_dict.update({str(col): val for col, val in zip(col_members, values)})
        rows.append(row_dict)

    return columns, rows, row_dims
