"""Functional tests using keboola.datadirtest with mocked Essbase API responses."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure src/ is importable so patches resolve to the right module
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from keboola.datadirtest import DataDirTester, TestDataDir

COMPONENT_SCRIPT = str(Path(__file__).parent.parent / "src" / "component.py")
FUNCTIONAL_DIR = str(Path(__file__).parent / "functional")

# Real Essbase 21C MDX response fixture (verified against test VM)
MDX_FIXTURE = {
    "metadata": {"page": [], "column": ["Year"], "row": ["Product"]},
    "data": [
        ["", "Jan", "Feb", "Mar"],
        ["Cola", 1710.0, 1666.0, 1842.0],
        ["Root Beer", 1615.0, 1654.0, 1723.0],
    ],
}


class HyperionTestDataDir(TestDataDir):
    """Runs the component with Essbase REST API calls mocked out."""

    def run_component(self):
        with (
            patch("essbase_client.EssbaseClient.verify_connection", return_value="21.0"),
            patch("essbase_client.EssbaseClient.execute_mdx", return_value=MDX_FIXTURE),
        ):
            super().run_component()


class TestFunctional(unittest.TestCase):
    def test_functional_suite(self):
        DataDirTester(
            data_dir=FUNCTIONAL_DIR,
            component_script=COMPONENT_SCRIPT,
            test_data_dir_class=HyperionTestDataDir,
        ).run()
