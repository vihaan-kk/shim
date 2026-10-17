import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.printer.octoprint_client import OctoPrintError
from tools.printer.readiness import check_printer_readiness


class FakeClient:
    def __init__(self, conn=None, printer=None, job=None, error=None):
        self._conn = conn or {"current": {"state": "Operational", "port": "VIRTUAL"}}
        self._printer = printer or {"state": {"flags": {"operational": True, "printing": False}}}
        self._job = job or {"state": "Operational", "progress": {"completion": None}}
        self._error = error

    def connection(self):
        if self._error:
            raise self._error
        return self._conn

    def printer(self):
        return self._printer

    def job(self):
        return self._job


class ReadinessTests(unittest.TestCase):
    def test_ready_on_virtual_port(self):
        r = check_printer_readiness(FakeClient()).to_dict()
        self.assertEqual(r["status"], "success")
        self.assertTrue(r["data"]["ready"])

    def test_physical_port_fails(self):
        c = FakeClient(conn={"current": {"state": "Operational", "port": "/dev/ttyUSB0"}})
        r = check_printer_readiness(c).to_dict()
        self.assertFalse(r["data"]["ready"])
        self.assertIn("port_mismatch", r["data"]["reasons"])

    def test_printing_is_not_ready(self):
        c = FakeClient(
            conn={"current": {"state": "Printing", "port": "VIRTUAL"}},
            printer={"state": {"flags": {"operational": True, "printing": True}}},
        )
        r = check_printer_readiness(c).to_dict()
        self.assertFalse(r["data"]["ready"])
        self.assertIn("busy_or_error", r["data"]["reasons"])

    def test_not_operational_409(self):
        r = check_printer_readiness(FakeClient(error=OctoPrintError("x", 409))).to_dict()
        self.assertEqual(r["status"], "success")
        self.assertFalse(r["data"]["ready"])

    def test_unreachable_is_fatal(self):
        r = check_printer_readiness(FakeClient(error=OctoPrintError("down"))).to_dict()
        self.assertEqual(r["status"], "fatal")
        self.assertEqual(r["error"]["code"], "printer_unreachable")

    def test_bad_argument_is_fixable(self):
        r = check_printer_readiness(FakeClient(), expected_port="").to_dict()
        self.assertEqual(r["status"], "fixable")


if __name__ == "__main__":
    unittest.main()
