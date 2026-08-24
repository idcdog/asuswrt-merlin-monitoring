from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


def fixture(name: str) -> str:
    return (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")


def test_config() -> object:
    return wifi.Config(
        router_host="192.0.2.1",
        router_port=2222,
        router_user="root",
        interval_seconds=30,
        timeout_seconds=20,
        listen_host="127.0.0.1",
        listen_port=9101,
        management_host="127.0.0.1",
        management_port=9102,
        alias_file="unused",
        management_html="unused",
    )


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
wan_rx_bytes|342500000000
wan_tx_bytes|212900000000
wan_rx_packets|319600000
wan_tx_packets|313000000
wan_rx_errors|0
wan_tx_errors|0
wan_rx_dropped|0
wan_tx_dropped|4487
wan_speed_mbps|2500
wan_oper_up|1
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
        self.assertEqual(snapshot.wan_receive_bytes, 342_500_000_000)
        self.assertEqual(snapshot.wan_transmit_dropped, 4487)
        self.assertEqual(snapshot.wan_speed_bps, 2_500_000_000)
        self.assertEqual(snapshot.wan_oper_up, 1)
        self.assertEqual(snapshot.radios[1].band, "5G")
        self.assertAlmostEqual(snapshot.radios[0].utilization_ratio, 0.18)
        temperatures = dict(snapshot.temperatures)
        self.assertAlmostEqual(temperatures["cpu"], 74.1)

    def test_parse_system_rejects_incomplete_cpu_counters(self) -> None:
        with self.assertRaises(RuntimeError):
            wifi.parse_system("cpu_stat|1 2 3")

    def test_missing_wan_speed_is_not_published_as_zero(self) -> None:
        raw = fixture("rt-be88u-3006.102.8_4-full.txt").replace("wan_speed_mbps|2500\n", "")
        snapshot = wifi.parse_system(wifi.section(raw, "@@SYSTEM@@", "@@NMP@@"))
        self.assertIsNone(snapshot.wan_speed_bps)
        self.assertNotIn("asus_router_wan_speed_bps", wifi.render_system_metrics(snapshot))

    def test_missing_required_wan_counter_is_rejected(self) -> None:
        raw = fixture("rt-be88u-3006.102.8_4-full.txt").replace("wan_rx_bytes|342500000000\n", "")
        with self.assertRaisesRegex(RuntimeError, "required WAN counter wan_rx_bytes"):
            wifi.parse_system(wifi.section(raw, "@@SYSTEM@@", "@@NMP@@"))

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

    def test_full_collector_fixture(self) -> None:
        raw = fixture("rt-be88u-3006.102.8_4-full.txt")
        with tempfile.TemporaryDirectory() as directory:
            aliases = wifi.AliasStore(str(Path(directory) / "aliases.json"))
            with mock.patch.object(wifi, "ssh_collect", return_value=raw):
                metrics, snapshot, devices = wifi.collect_once(test_config(), aliases)
        self.assertEqual(snapshot.model, "RT-BE88U")
        self.assertEqual(
            [(radio.iface, radio.band) for radio in snapshot.radios],
            [("wl0", "2.4G"), ("wl1", "5G")],
        )
        self.assertIn("asus_wifi_stations 2\n", metrics)
        self.assertEqual(sum(bool(device["online"]) for device in devices), 2)
        system_metrics = wifi.render_system_metrics(snapshot)
        self.assertIn(
            'asus_router_wan_receive_bytes_total{interface="eth1"} 342500000000',
            system_metrics,
        )
        self.assertIn('asus_router_wan_speed_bps{interface="eth1"} 2500000000', system_metrics)

    def test_zero_station_fixture_is_healthy(self) -> None:
        raw = fixture("rt-be88u-3006.102.8_4-zero-stations.txt")
        with tempfile.TemporaryDirectory() as directory:
            aliases = wifi.AliasStore(str(Path(directory) / "aliases.json"))
            with mock.patch.object(wifi, "ssh_collect", return_value=raw):
                metrics, snapshot, devices = wifi.collect_once(test_config(), aliases)
        self.assertEqual(snapshot.uptime_seconds, 7200)
        self.assertIn("asus_wifi_stations 0\n", metrics)
        self.assertNotIn("asus_wifi_station_info{", metrics)
        self.assertEqual(len(devices), 1)
        self.assertFalse(devices[0]["online"])
        state = wifi.CollectorState()
        state.success(metrics, devices, 0.1)
        rendered, healthy = state.render(30)
        self.assertTrue(healthy)
        self.assertIn("asus_wifi_stations 0\n", rendered)
        self.assertIn("asus_wifi_exporter_collection_errors_total 0", rendered)

    def test_wireless_command_error_is_not_zero_stations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            aliases = wifi.AliasStore(str(Path(directory) / "aliases.json"))
            with mock.patch.object(
                wifi, "ssh_collect", return_value=fixture("wireless-command-error.txt")
            ):
                with self.assertRaisesRegex(RuntimeError, "wl1"):
                    wifi.collect_once(test_config(), aliases)

    def test_truncated_station_block_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            aliases = wifi.AliasStore(str(Path(directory) / "aliases.json"))
            with mock.patch.object(
                wifi, "ssh_collect", return_value=fixture("wireless-malformed.txt")
            ):
                with self.assertRaisesRegex(RuntimeError, "expected 1, parsed 0"):
                    wifi.collect_once(test_config(), aliases)

    def test_six_ghz_band_comes_from_discovered_radio(self) -> None:
        raw = fixture("tri-band-6ghz.txt")
        system = wifi.parse_system(wifi.section(raw, "@@SYSTEM@@", "@@NMP@@"))
        stations = wifi.parse_station_blocks(
            raw,
            wifi.parse_nmp(wifi.section(raw, "@@NMP@@", "@@LEASES@@")),
            wifi.parse_leases(wifi.section(raw, "@@LEASES@@", "@@ARP@@")),
            {radio.iface: radio.band for radio in system.radios},
        )
        self.assertEqual(stations[0].band, "6G")
        self.assertEqual(stations[0].values["channel"], 5)
        self.assertIn(("wifi_6ghz", 62.0), system.temperatures)


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
