from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


wifi = load_module("asus_wifi_exporter", "src/asus_wifi_exporter.py")
traffic = load_module("asus_traffic_importer", "src/asus_traffic_importer.py")


class WifiExporterTests(unittest.TestCase):
    def test_normalize_mac(self) -> None:
        self.assertEqual(wifi.normalize_mac("02:aa:bb:cc:dd:ee"), "02:AA:BB:CC:DD:EE")
        with self.assertRaises(ValueError):
            wifi.normalize_mac("not-a-mac")

    def test_cpu_usage_ratio(self) -> None:
        previous = (100.0, 0.0, 50.0, 850.0)
        current = (120.0, 0.0, 60.0, 920.0)
        self.assertAlmostEqual(wifi.cpu_usage_ratio(current, previous), 0.3)


class TrafficImporterTests(unittest.TestCase):
    def test_build_payload(self) -> None:
        rows = "3600|02:AA:BB:CC:DD:EE|100|200\n7200|02:AA:BB:CC:DD:EE|300|400"
        payload, buckets, devices, latest = traffic.build_payload(
            rows,
            {"02:AA:BB:CC:DD:EE": "Living Room"},
            "ASUS Router",
        )
        rendered = payload.decode()
        self.assertEqual((buckets, devices, latest), (2, 1, 7200))
        self.assertIn('name="Living Room"', rendered)
        self.assertIn('device="ASUS Router"', rendered)
        self.assertEqual(rendered.count("\n"), 4)

    def test_rejects_negative_traffic(self) -> None:
        with self.assertRaises(RuntimeError):
            traffic.build_payload("3600|02:AA:BB:CC:DD:EE|-1|2", {}, "router")


if __name__ == "__main__":
    unittest.main()
