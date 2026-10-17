from tools.printer.octoprint_client import OctoPrintError
from tools.printer.tools import read_printer_status


class FakeClient:
    def __init__(self, port="VIRTUAL", flags=None, state="Operational", error=None, printer_error=None):
        self._conn = {"current": {"state": state, "port": port}}
        self._flags = flags if flags is not None else {"operational": True}
        self._error = error
        self._printer_error = printer_error

    def connection(self):
        if self._error:
            raise self._error
        return self._conn

    def printer(self):
        if self._printer_error:
            raise self._printer_error
        return {"state": {"flags": self._flags}}

    def job(self):
        return {"state": "Operational", "progress": {"completion": None}}


def test_ready_on_virtual_port():
    r = read_printer_status(FakeClient()).to_dict()
    assert r["status"] == "success" and r["data"]["ready"] is True


def test_physical_port_fails_readiness():
    r = read_printer_status(FakeClient(port="/dev/ttyUSB0")).to_dict()
    assert r["data"]["ready"] is False and "port_mismatch" in r["data"]["reasons"]


def test_printing_is_not_ready():
    c = FakeClient(flags={"operational": True, "printing": True}, state="Printing")
    r = read_printer_status(c).to_dict()
    assert r["data"]["ready"] is False and "busy_or_error" in r["data"]["reasons"]


def test_409_means_not_operational():
    r = read_printer_status(FakeClient(printer_error=OctoPrintError("x", 409))).to_dict()
    assert r["status"] == "success" and "not_operational" in r["data"]["reasons"]


def test_unreachable_is_fatal():
    r = read_printer_status(FakeClient(error=OctoPrintError("down"))).to_dict()
    assert r["status"] == "fatal" and r["error"]["code"] == "printer_unreachable"
