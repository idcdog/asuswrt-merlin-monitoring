from __future__ import annotations

import importlib.util
import sys
import tempfile
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

    def test_parse_system_snapshot(self) -> None:
        raw = """\
productid|RT-BE88U
firmver|3.0.0.6
buildno|102.8
extendno|4
innerver|example
wan_interface|eth1
wan_protocol|dhcp
wan_private_ipv4|192.0.2.2
wan_public_ipv4|198.51.100.2
wan_link_up|1
uptime_seconds|3600.5
load1|0.25
load5|0.20
load15|0.15
cpu_cores|4
cpu_stat|100 10 20 800 20 0 0 0
memtotal_kb|2048000
memavailable_kb|1024000
swaptotal_kb|100
swapfree_kb|80
conntrack_count|4368
conntrack_max|300000
conntrack_active|429
cpu_temp_millicelsius|74100
wl0_temp_c|75
wl1_temp_c|74
radio_wl0|2.4G|6|18|-92
radio_wl1|5G|149|12|-96
"""
        snapshot = wifi.parse_system(raw)
        self.assertEqual(snapshot.model, "RT-BE88U")
        self.assertEqual(snapshot.firmware, "3006.102.8_4")
        self.assertEqual(snapshot.memory_total_bytes, 2048000 * 1024)
        self.assertEqual(snapshot.conntrack_active, 429)
        self.assertEqual(snapshot.radios[1].band, "5G")
        self.assertAlmostEqual(snapshot.radios[0].utilization_ratio, 0.18)
        temperatures = dict(snapshot.temperatures)
        self.assertAlmostEqual(temperatures["cpu"], 74.1)

    def test_parse_system_rejects_incomplete_cpu_counters(self) -> None:
        with self.assertRaises(RuntimeError):
            wifi.parse_system("cpu_stat|1 2 3")

    def test_parse_wireless_station(self) -> None:
        raw = """\
@@STA wl1.1 02:AA:BB:CC:DD:EE
in network 120 seconds
idle 3 seconds
chanspec 149/80
smoothed rssi: -55
per antenna noise floor: -95 -93 -94
rate of last tx pkt: 1200000 kbps
rate of last rx pkt: 600000 kbps
tx ucast bytes: 12345
rx ucast bytes: 67890
@@END@@
"""
        clients = {
            "02:AA:BB:CC:DD:EE": {"name": "Example Client", "vendor": "Example Vendor"}
        }
        leases = {"02:AA:BB:CC:DD:EE": ("192.0.2.10", "lease-name")}
        stations = wifi.parse_station_blocks(raw, clients, leases)
        self.assertEqual(len(stations), 1)
        station = stations[0]
        self.assertEqual(station.band, "5G")
        self.assertEqual(station.identity.name, "Example Client")
        self.assertEqual(station.identity.ip, "192.0.2.10")
        self.assertEqual(station.values["tx_rate_bps"], 1_200_000_000)
        self.assertEqual(station.values["snr_db"], 39)

    def test_alias_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "device-names.json")
            store = wifi.AliasStore(path)
            store.set("02:aa:bb:cc:dd:ee", "Example Device")
            self.assertEqual(store.snapshot(), {"02:AA:BB:CC:DD:EE": "Example Device"})
            store.delete("02:AA:BB:CC:DD:EE")
            self.assertEqual(store.snapshot(), {})


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

    def test_split_sections_and_parse_names(self) -> None:
        raw = '@@NMP@@\n{"02:AA:BB:CC:DD:EE":{"name":"Example"}}\n@@DATA@@\n3600|02:AA:BB:CC:DD:EE|1|2\n'
        names_raw, rows = traffic.split_sections(raw)
        self.assertEqual(traffic.parse_names(names_raw), {"02:AA:BB:CC:DD:EE": "Example"})
        self.assertEqual(rows, "3600|02:AA:BB:CC:DD:EE|1|2")


if __name__ == "__main__":
    unittest.main()
