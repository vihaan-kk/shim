"""Small OctoPrint REST client (stdlib only).

The API key is held here and never returned to callers. A 2xx/204 reply to a
command means "accepted", not "done"; callers must read state back with GET.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


class OctoPrintError(Exception):
    """Transport failure or unexpected HTTP status."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class OctoPrintClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0):
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self._base + path, data=data, method=method)
        req.add_header("X-Api-Key", self._key)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise OctoPrintError(f"{method} {path} returned HTTP {e.code}", e.code) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            # str(e) can echo the URL but never the key header.
            raise OctoPrintError(f"{method} {path} failed: {type(e).__name__}") from None

    def connection(self) -> dict:
        return self._request("GET", "/api/connection")

    def printer(self) -> dict:
        return self._request("GET", "/api/printer")

    def job(self) -> dict:
        return self._request("GET", "/api/job")

    def select_file(self, location: str, path: str) -> None:
        """Select a stored file with print=false; starting is a separate call."""
        self._request("POST", f"/api/files/{location}/{path}", {"command": "select", "print": False})

    def start_job(self) -> None:
        self._request("POST", "/api/job", {"command": "start"})

    def pause_job(self) -> None:
        self._request("POST", "/api/job", {"command": "pause", "action": "pause"})
