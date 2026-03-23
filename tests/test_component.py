import os
import unittest
from unittest import mock

from keboola.component.exceptions import UserException

from component import Component


class TestComponent(unittest.TestCase):
    @mock.patch.dict(os.environ, {"KBC_DATADIR": "./non-existing-dir"})
    def test_run_no_cfg_fails(self):
        with self.assertRaises((UserException, ValueError)):
            comp = Component()
            comp.run()


if __name__ == "__main__":
    unittest.main()
