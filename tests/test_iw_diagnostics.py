import unittest
import time
from pathlib import Path

from web_measurement_app.logger_core import (
    HEADERS,
    IW_HEADERS,
    LEGACY_HEADERS,
    PING_STAT_HEADERS,
    RUNTIME_HEADERS,
    SURVEY_HEADERS,
    build_nmcli_command,
    parse_iw_survey_dump,
    parse_iw_station_dump,
)
from web_measurement_app.service import MeasurementConfig, MeasurementService


EXPECTED_LEGACY_HEADERS = [
    "Index",
    "Point",
    "Date",
    "Time",
    "SSID",
    "BSSID",
    "Channel",
    "Rate",
    "SignalStrength",
    "dBm",
    "icmp_seq",
    "ttl",
    "time_ms",
    "Status",
    "neighbor_scan_ran",
    "neighbor_match_ssid",
    "neighbor_count_visible",
    "neighbor_count_same_ssid",
    "neighbor_bssid_list",
    "best_neighbor_ssid",
    "best_neighbor_bssid",
    "best_neighbor_channel",
    "best_neighbor_rate",
    "best_neighbor_signal",
    "best_neighbor_dbm",
    "best_neighbor_signal_gap",
    "ArpTargetState",
    "PingTarget",
    "PingTargetSource",
    "Host",
    "SshStatus",
    "Error",
]


class IwDiagnosticsTest(unittest.TestCase):
    def test_regular_nmcli_capture_never_triggers_rescan(self):
        command = build_nmcli_command(False)
        self.assertEqual(command[-3:], ["list", "--rescan", "no"])

    def test_default_output_directory_is_this_version(self):
        config = MeasurementConfig()
        expected = str(Path(__file__).resolve().parent.parent)
        self.assertEqual(config.output_dir, expected)

    def test_legacy_columns_are_unchanged_and_first(self):
        self.assertEqual(LEGACY_HEADERS, EXPECTED_LEGACY_HEADERS)
        self.assertEqual(HEADERS[: len(LEGACY_HEADERS)], EXPECTED_LEGACY_HEADERS)
        iw_start = len(LEGACY_HEADERS)
        ping_start = iw_start + len(IW_HEADERS)
        runtime_start = ping_start + len(PING_STAT_HEADERS)
        survey_start = runtime_start + len(RUNTIME_HEADERS)
        self.assertEqual(HEADERS[iw_start:ping_start], IW_HEADERS)
        self.assertEqual(HEADERS[ping_start:runtime_start], PING_STAT_HEADERS)
        self.assertEqual(HEADERS[runtime_start:survey_start], RUNTIME_HEADERS)
        self.assertEqual(HEADERS[survey_start:], SURVEY_HEADERS)

    def test_station_dump_parser(self):
        output = """Station 30:de:4b:4a:12:67 (on wlan0)
\tinactive time:\t20 ms
\ttx packets:\t100
\ttx retries:\t7
\ttx failed:\t2
\tbeacon loss:\t1
\trx drop misc:\t3
\tsignal:\t-68 [-70, -67] dBm
\tsignal avg:\t-66 dBm
\tbeacon signal avg:\t-65 dBm
\ttx bitrate:\t1201.0 MBit/s HE-MCS 11 HE-NSS 2 80MHz
\trx bitrate:\t573.5 MBit/s VHT-MCS 7 VHT-NSS 2 80MHz
"""
        info = parse_iw_station_dump(output)

        self.assertEqual(info["IwSampleValid"], "yes")
        self.assertEqual(info["IwStationBssid"], "30:DE:4B:4A:12:67")
        self.assertEqual(info["IwSignalDbm"], "-68")
        self.assertEqual(info["IwChainSignalDbm"], "-70|-67")
        self.assertEqual(info["IwTxMcs"], "11")
        self.assertEqual(info["IwTxNss"], "2")
        self.assertEqual(info["IwRxMcs"], "7")
        self.assertEqual(info["IwRxNss"], "2")
        self.assertEqual(info["IwChannelWidthMhz"], "80")

    def test_counter_deltas_only_use_same_bssid(self):
        service = MeasurementService()
        first = {
            "IwSampleValid": "yes",
            "IwStationBssid": "30:DE:4B:4A:12:67",
            "IwTxPacketsTotal": "100",
            "IwTxRetriesTotal": "7",
            "IwTxFailedTotal": "2",
        }
        second = {
            "IwSampleValid": "yes",
            "IwStationBssid": "30:DE:4B:4A:12:67",
            "IwTxPacketsTotal": "120",
            "IwTxRetriesTotal": "9",
            "IwTxFailedTotal": "3",
        }

        prepared_first = service._prepare_iw_info(first, "30:de:4b:4a:12:67")
        prepared_second = service._prepare_iw_info(second, "30:de:4b:4a:12:67")

        self.assertEqual(prepared_first["IwTxPacketsDelta"], "")
        self.assertEqual(prepared_second["IwTxPacketsDelta"], "20")
        self.assertEqual(prepared_second["IwTxRetriesDelta"], "2")
        self.assertEqual(prepared_second["IwTxFailedDelta"], "1")
        self.assertEqual(prepared_second["IwTxRetryRatePct"], "10.000")
        self.assertEqual(prepared_second["IwTxFailedRatePct"], "5.000")

    def test_bssid_mismatch_does_not_write_stale_iw_values(self):
        service = MeasurementService()
        info = {
            "IwSampleValid": "yes",
            "IwStationBssid": "30:DE:4B:4A:12:67",
            "IwSignalDbm": "-68",
            "IwTxPacketsTotal": "100",
        }

        prepared = service._prepare_iw_info(info, "78:8C:B5:9A:DE:29")

        self.assertTrue(all(prepared[key] == "" for key in IW_HEADERS))

    def test_ping_statistics_use_existing_samples_only(self):
        service = MeasurementService()
        config = MeasurementConfig(ping_stats_window_sec=30)
        first = service._ping_stat_columns("10", "ok", config)
        second = service._ping_stat_columns("20", "ok", config)
        timeout = service._ping_stat_columns("999", "ping_timeout", config)

        self.assertEqual(first[0:3], ["1", "1", "0.000"])
        self.assertEqual(second[0:5], ["2", "2", "0.000", "15.000", "15.000"])
        self.assertEqual(timeout[0:3], ["3", "2", "33.333"])

    def test_runtime_diagnostics_append_after_existing_columns(self):
        service = MeasurementService()
        service._config = MeasurementConfig(survey_enabled=False)
        service._begin_sample()
        line = ["" for _header in LEGACY_HEADERS + IW_HEADERS]
        line[12] = "12.5"
        line[13] = "ok"

        service._append_runtime_diagnostics(line)

        self.assertEqual(len(line), len(HEADERS))
        self.assertEqual(line[len(LEGACY_HEADERS) + len(IW_HEADERS)], "1")
        self.assertTrue(line[len(LEGACY_HEADERS) + len(IW_HEADERS) + len(PING_STAT_HEADERS)] != "")
        self.assertTrue(all(value == "" for value in line[-len(SURVEY_HEADERS) :]))

    def test_survey_is_not_started_by_default(self):
        service = MeasurementService()
        service._schedule_survey(MeasurementConfig(survey_enabled=False))

        self.assertIsNone(service._survey_thread)

    def test_survey_parser_uses_in_use_channel(self):
        output = """Survey data from wlan0
	frequency:                      5180 MHz [in use]
	noise:                          -95 dBm
	channel active time:            1000 ms
	channel busy time:              250 ms
	channel receive time:           125 ms
	channel transmit time:          50 ms
Survey data from wlan0
	frequency:                      5200 MHz
	channel active time:            9999 ms
"""
        info = parse_iw_survey_dump(output)
        self.assertEqual(info["SurveySampleValid"], "yes")
        self.assertEqual(info["SurveyFrequencyMhz"], "5180")
        self.assertEqual(info["SurveyNoiseDbm"], "-95")
        self.assertEqual(info["SurveyBusyMsTotal"], "250")

    def test_survey_busy_rate_uses_counter_deltas(self):
        service = MeasurementService()
        config = MeasurementConfig(survey_enabled=True)
        first = {
            "SurveySampleValid": "yes",
            "SurveyFrequencyMhz": "5180",
            "SurveyNoiseDbm": "-95",
            "SurveyActiveMsTotal": "1000",
            "SurveyBusyMsTotal": "250",
            "SurveyRxMsTotal": "125",
            "SurveyTxMsTotal": "50",
        }
        second = {**first, "SurveyActiveMsTotal": "1400", "SurveyBusyMsTotal": "450"}
        with service._survey_lock:
            service._pending_survey_result = {"info": first, "captured_monotonic": time.monotonic()}
        initial = service._survey_columns(config)
        with service._survey_lock:
            service._pending_survey_result = {"info": second, "captured_monotonic": time.monotonic()}
        updated = service._survey_columns(config)

        self.assertEqual(initial[SURVEY_HEADERS.index("SurveyActiveMsDelta")], "")
        self.assertEqual(updated[SURVEY_HEADERS.index("SurveyActiveMsDelta")], "400")
        self.assertEqual(updated[SURVEY_HEADERS.index("SurveyBusyMsDelta")], "200")
        self.assertEqual(updated[SURVEY_HEADERS.index("SurveyBusyRatePct")], "50.000")


if __name__ == "__main__":
    unittest.main()
