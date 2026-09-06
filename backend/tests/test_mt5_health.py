from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from app.services import mt5_client as module
from main import health


class ConnectionTests(TestCase):
    def test_retry_counts_native_call_time_in_budget(self):
        clock = [0.0]

        def initialize(*args, **kwargs):
            clock[0] += kwargs["timeout"] / 1000
            return False

        fake = SimpleNamespace(
            initialize=Mock(side_effect=initialize),
            last_error=Mock(return_value=(-10005, "IPC timeout")),
            shutdown=Mock(),
        )
        with (
            patch.object(module, "mt5", fake),
            patch.object(module.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(module.time, "sleep", side_effect=lambda n: clock.__setitem__(0, clock[0] + n)),
        ):
            self.assertFalse(module.MT5Client()._initialize_with_retry("terminal.exe"))
        self.assertEqual(clock[0], 70)
        self.assertEqual(fake.initialize.call_count, 3)

    def test_retry_success_returns_without_more_attempts(self):
        fake = SimpleNamespace(
            initialize=Mock(side_effect=[False, True]),
            last_error=Mock(return_value=(-10005, "IPC timeout")),
            shutdown=Mock(),
        )
        with patch.object(module, "mt5", fake), patch.object(module.time, "sleep"):
            self.assertTrue(module.MT5Client()._initialize_with_retry("terminal.exe"))
        self.assertEqual(fake.initialize.call_count, 2)
        fake.shutdown.assert_called_once()

    def test_health_detects_lost_broker_connection(self):
        client = module.MT5Client()
        client._connected = True
        fake = SimpleNamespace(
            terminal_info=Mock(return_value=SimpleNamespace(connected=False)),
            account_info=Mock(return_value=SimpleNamespace(trade_mode=0)),
        )
        with patch.object(module, "MT5_AVAILABLE", True), patch.object(module, "mt5", fake):
            self.assertFalse(client.connection_health()["connected"])
            fake.terminal_info.return_value.connected = True
            self.assertEqual(client.connection_health(), {"connected": True, "verified_type": "DEMO"})

    def test_health_payload_reports_degraded_and_recovers(self):
        for connected, expected in [(False, "degraded"), (True, "ok")]:
            with patch("main.mt5_client.connection_health", return_value={"connected": connected}):
                self.assertEqual(health()["status"], expected)
