import os
import unittest

from unittest import mock

from component import Component
from keboola.component.exceptions import UserException


class TestComponent(unittest.TestCase):
    @mock.patch.dict(os.environ, {"KBC_DATADIR": "./non-existing-dir"})
    def test_run_no_cfg_fails(self):
        with self.assertRaises((UserException, Exception)):
            comp = Component()
            comp.run()


if __name__ == "__main__":
    unittest.main()
