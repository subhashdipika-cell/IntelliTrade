from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.services import mt5_client as mt5_module
from app.workers import scheduler
from app.workers import signal_scanner as scanner_module


class _FakeScheduler:
    def __init__(self, *, daemon: bool) -> None:
        self.daemon = daemon
        self.jobs: list[tuple[object, dict]] = []
        self.started = False

    def add_job(self, func, **kwargs) -> None:
        self.jobs.append((func, kwargs))

    def start(self) -> None:
        self.started = True

    def shutdown(self, *, wait: bool) -> None:
        self.started = False


class SchedulerCadenceTests(unittest.TestCase):
    def test_scanner_runs_immediately_then_every_sixty_seconds(self) -> None:
        fake = _FakeScheduler(daemon=True)
        scheduler._scheduler = None
        try:
            with (
                patch.object(scheduler, "BackgroundScheduler", return_value=fake),
                patch.object(scheduler, "_keep_awake"),
            ):
                scheduler.start_scheduler()

            jobs = {kwargs["id"]: kwargs for _, kwargs in fake.jobs}
            scan = jobs["signal_scanner"]
            self.assertEqual(scheduler.SCAN_SECONDS, 60)
            self.assertEqual(scan["seconds"], 60)
            self.assertEqual(scan["max_instances"], 1)
            self.assertTrue(scan["coalesce"])
            self.assertEqual(scan["misfire_grace_time"], 60)
            self.assertIsInstance(scan["next_run_time"], datetime)
            self.assertTrue(fake.started)
        finally:
            scheduler._scheduler = None


class TerminalBindingTests(unittest.TestCase):
    def test_configured_terminal_failure_does_not_fall_back(self) -> None:
        fake_mt5 = SimpleNamespace(
            initialize=unittest.mock.Mock(return_value=False),
            last_error=unittest.mock.Mock(return_value=(-10004, "No IPC connection")),
        )
        client = mt5_module.MT5Client()
        terminal = r"D:\MT5IntelliTrade\terminal64.exe"

        with (
            patch.object(mt5_module, "MT5_AVAILABLE", True),
            patch.object(mt5_module, "mt5", fake_mt5),
            patch.object(mt5_module.os.path, "exists", return_value=True),
            patch.object(
                type(mt5_module.settings),
                "terminal_path_for",
                return_value=terminal,
            ),
        ):
            self.assertFalse(client.connect())

        fake_mt5.initialize.assert_called_once_with(path=terminal)


class ScannerHeartbeatTests(unittest.TestCase):
    def test_disabled_scan_still_records_the_minute_heartbeat(self) -> None:
        scanner = scanner_module.SignalScanner()
        disabled = SimpleNamespace(enabled=False, mode="autonomous")

        with patch.object(scanner_module.scanner_settings, "get", return_value=disabled):
            scanner.scan()
            status = scanner.status()

        self.assertEqual(status["scan_interval_seconds"], 60)
        self.assertEqual(status["scan_count"], 1)
        self.assertIsNotNone(status["last_scan_started_at"])
        self.assertIsNotNone(status["last_scan_completed_at"])


if __name__ == "__main__":
    unittest.main()
