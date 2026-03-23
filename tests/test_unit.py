"""Unit tests for parser functions — no API calls required."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from essbase_client import mdx_response_to_rows
from planning_client import planning_export_to_rows


class TestMdxResponseToRows(unittest.TestCase):
    def test_basic_parse(self):
        response = {
            "metadata": {"page": [], "column": ["Year"], "row": ["Product"]},
            "data": [
                ["", "Jan", "Feb", "Mar"],
                ["Cola", 1710.0, 1666.0, 1842.0],
                ["Root Beer", 1615.0, 1654.0, 1723.0],
            ],
        }
        columns, rows = mdx_response_to_rows(response)

        self.assertEqual(columns, ["Product", "Jan", "Feb", "Mar"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"Product": "Cola", "Jan": 1710.0, "Feb": 1666.0, "Mar": 1842.0})
        self.assertEqual(rows[1], {"Product": "Root Beer", "Jan": 1615.0, "Feb": 1654.0, "Mar": 1723.0})

    def test_empty_data(self):
        columns, rows = mdx_response_to_rows({"metadata": {}, "data": []})
        self.assertEqual(columns, [])
        self.assertEqual(rows, [])

    def test_missing_metadata_uses_default_row_name(self):
        response = {
            "metadata": {},
            "data": [
                ["", "Q1"],
                ["Sales", 500.0],
            ],
        }
        columns, rows = mdx_response_to_rows(response)
        self.assertEqual(columns[0], "row")

    def test_single_row_single_column(self):
        response = {
            "metadata": {"row": ["Account"]},
            "data": [
                ["", "FY2024"],
                ["Revenue", 999.9],
            ],
        }
        columns, rows = mdx_response_to_rows(response)
        self.assertEqual(columns, ["Account", "FY2024"])
        self.assertEqual(rows[0], {"Account": "Revenue", "FY2024": 999.9})


class TestPlanningExportToRows(unittest.TestCase):
    def test_basic_parse(self):
        response = {
            "headers": ["Account", "Period", "Value"],
            "rows": [["Sales", "Jan", 1000], ["COGS", "Jan", 500]],
        }
        columns, rows = planning_export_to_rows(response)

        self.assertEqual(columns, ["Account", "Period", "Value"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"Account": "Sales", "Period": "Jan", "Value": 1000})

    def test_empty_response(self):
        columns, rows = planning_export_to_rows({})
        self.assertEqual(columns, [])
        self.assertEqual(rows, [])

    def test_headers_no_rows(self):
        response = {"headers": ["Dim1", "Dim2"], "rows": []}
        columns, rows = planning_export_to_rows(response)
        self.assertEqual(columns, ["Dim1", "Dim2"])
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
