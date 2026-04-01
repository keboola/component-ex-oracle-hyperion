import logging
from typing import Any

import requests
from keboola.component.exceptions import UserException


class PlanningClient:
    """Client for Hyperion Planning REST API (port 9000, CSS SSO token auth)."""

    API_PATH = "/HyperionPlanning/rest/v3"

    def __init__(self, base_url: str, username: str, password: str, ssl_verify: bool = True):
        self.base_url = base_url.rstrip("/")
        self.ssl_verify = ssl_verify
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        token = self._login(username, password)
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _login(self, username: str, password: str) -> str:
        url = f"{self.base_url}/interop/logon"
        try:
            resp = self.session.post(
                url,
                json={"username": username, "password": password},
                verify=self.ssl_verify,
                timeout=60,
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise UserException(f"Planning authentication failed [{e.response.status_code}]: {e.response.text}") from e
        except requests.ConnectionError as e:
            raise UserException(f"Cannot connect to Planning server at {self.base_url}: {e}") from e

        data = resp.json()
        token = data.get("token") or data.get("userToken")
        if not token:
            raise UserException(f"Planning login succeeded but no token found in response: {data}")
        logging.debug("Planning authentication successful.")
        return token

    def get_applications(self) -> list[dict]:
        return self._get("/applications").get("items", [])

    def export_data_slice(self, application: str, plan_type: str, payload: dict) -> dict:
        return self._post(f"/applications/{application}/plantypes/{plan_type}/exportdataslice", payload)

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{self.API_PATH}{path}"
        try:
            resp = self.session.get(url, verify=self.ssl_verify, timeout=300)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            raise UserException(
                f"Planning API error [{e.response.status_code}] on GET {path}: {e.response.text}"
            ) from e
        except requests.ConnectionError as e:
            raise UserException(f"Cannot connect to Planning server at {self.base_url}: {e}") from e

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self.base_url}{self.API_PATH}{path}"
        try:
            resp = self.session.post(url, json=payload, verify=self.ssl_verify, timeout=300)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            raise UserException(
                f"Planning API error [{e.response.status_code}] on POST {path}: {e.response.text}"
            ) from e
        except requests.ConnectionError as e:
            raise UserException(f"Cannot connect to Planning server at {self.base_url}: {e}") from e


def planning_export_to_rows(export_response: dict) -> tuple[list[str], list[dict]]:
    """
    Parse Planning exportdataslice response into (column_names, rows).

    Planning export response structure:
    {
      "headers": ["Account", "Period", "Value"],
      "rows": [["Sales", "Jan", 1000], ["COGS", "Jan", 500]]
    }
    """
    headers = export_response.get("headers", [])
    raw_rows = export_response.get("rows", [])

    if not headers:
        logging.warning("Planning export response contained no headers.")
        return [], []

    rows = [dict(zip(headers, row)) for row in raw_rows]
    return headers, rows
