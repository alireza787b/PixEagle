"""Socket-free regression tests from the 2026-09-17 Topotek bench captures."""

import unittest
from unittest.mock import Mock, patch

from classes.gimbal_interface import ConnectionStatus, GimbalInterface
from classes.gimbal_types import CoordinateSystem, TrackingState


# Exact captured replies, including vendor checksum; no synthesized angles.
BODY = b"#tpGPCrGAC0122016A024F97"
SPATIAL = b"#tpGPCrGIA00ED000000008D"
ACTIVE = b"#TPDP2rTRC024A"
# Previously interpreted as angles after UTF-8 replacement decoding.
TRACKING_BOX = bytes.fromhex("237470445039774f46544403080232002600323046")


def frame(body):
    return body + f"{sum(body) & 255:02X}".encode("ascii")


class GimbalProtocolTest(unittest.TestCase):
    def setUp(self):
        self.interface = GimbalInterface()

    def ingest(self, packet, now):
        parsed = self.interface._parse_gimbal_packet(packet)
        self.assertIsNotNone(parsed)
        with self.interface.lock:
            return self.interface._ingest_parsed_data_locked(
                parsed, parsed.raw_packet, now=now,
            )

    def test_captured_body_reply_decodes_centidegrees(self):
        data = self.interface._parse_gimbal_packet(BODY)
        self.assertEqual(data.angles.to_tuple(), (2.9, 3.62, 5.91))
        self.assertEqual(data.coordinate_system, CoordinateSystem.GIMBAL_BODY)

    def test_signed_body_reply(self):
        data = self.interface._parse_gimbal_packet(frame(b"#tpGPCrGACFF9C0000FFCE"))
        self.assertEqual(data.angles.to_tuple(), (-1.0, 0.0, -0.5))

    def test_checksum_corruption_never_refreshes_tracking(self):
        self.ingest(ACTIVE, now=10.0)
        self.assertIsNone(self.interface._parse_gimbal_packet(b"#TPDP2rTRC0248"))
        self.assertEqual(self.interface.last_tracking_update_time, 10.0)

    def test_exact_header_addresses_lengths_and_hex_required(self):
        invalid = [
            frame(b"#tpGPCrGAC0122016A024Fextra"),
            frame(b"#tpGP2rGAC0122016A024F"),
            frame(b"#tpGPCrGAC0122016A024Z"),
            frame(b"#tpPGCrGAC0122016A024F"),
            frame(b"#TPPD2rTRC02"),  # request echo is not a response
            frame(b"#TPDP2rTRCx2"),
            BODY + b"\n",
            BODY[:-1],
        ]
        for packet in invalid:
            with self.subTest(packet=packet):
                self.assertIsNone(self.interface._parse_gimbal_packet(packet))

    def test_source_ip_rejected_before_any_state_mutation(self):
        self.assertIsNone(self.interface._parse_gimbal_packet(
            ACTIVE, source_ip="192.168.0.109",
        ))
        self.assertIsNotNone(self.interface._parse_gimbal_packet(
            ACTIVE, source_ip=self.interface.gimbal_ip,
        ))
        self.assertIsNone(self.interface.current_tracking_status)

    def test_listener_enforces_ip_without_requiring_command_source_port(self):
        for source_ip, expected in (("192.168.0.109", None),
                                    (self.interface.gimbal_ip, TrackingState.TRACKING_ACTIVE)):
            with self.subTest(source_ip=source_ip):
                interface = GimbalInterface()

                def receive(_size):
                    interface.running = False
                    return ACTIVE, (source_ip, 59598)

                interface.listen_socket = Mock()
                interface.listen_socket.recvfrom.side_effect = receive
                interface.running = True
                interface._listener_loop()
                self.assertEqual(interface.get_tracking_status(), expected)
                if expected is None:
                    self.assertEqual(interface.invalid_packets_received, 1)
                    self.assertEqual(interface.connection_status, ConnectionStatus.DISCONNECTED)

    def test_oft_cannot_become_angles_or_tracking_status(self):
        self.assertIsNone(self.interface._parse_gimbal_packet(TRACKING_BOX))
        self.assertIsNone(self.interface._parse_angle_response(TRACKING_BOX))
        self.assertIsNone(self.interface._parse_angle_response(
            TRACKING_BOX.decode("utf-8", errors="replace"),
        ))

    def test_spatial_packets_never_replace_or_refresh_body_angles(self):
        self.ingest(BODY, now=10.0)
        result = self.ingest(SPATIAL, now=10.5)
        self.assertEqual(result.angles.to_tuple(), (2.9, 3.62, 5.91))
        self.assertEqual(self.interface.last_data_time, 10.0)
        self.assertEqual(self.interface.last_spatial_packet, SPATIAL.decode())
        self.assertIsNone(self.ingest(SPATIAL, now=13.0))
        self.assertEqual(self.interface.last_data_time, 10.0)
        self.assertIsNone(self.interface._parse_angle_response(SPATIAL))

    def test_gic_is_diagnostic_and_cannot_supply_first_angle_sample(self):
        self.assertIsNone(self.ingest(frame(b"#tpGPCrGIC000000000000"), now=1.0))
        self.assertIsNone(self.interface.current_angles)
        self.assertIsNone(self.interface.last_data_time)

    def test_unsupported_and_lost_states_clear_previous_active_status(self):
        for code, expected in ((b"04", TrackingState.UNSUPPORTED),
                               (b"03", TrackingState.TARGET_LOST),
                               (b"01", TrackingState.TARGET_SELECTION),
                               (b"00", TrackingState.DISABLED)):
            with self.subTest(code=code):
                self.ingest(ACTIVE, now=10.0)
                result = self.ingest(frame(b"#TPDP2rTRC" + code), now=10.5)
                self.assertEqual(result.tracking_status.state, expected)
                self.assertFalse(result.is_tracking_active())

    def test_query_families_are_not_starved_when_due_together(self):
        interface = self.interface
        interface.query_tracking_status = Mock()
        interface.query_gimbal_body_angles = Mock()
        interface.query_spatial_fixed_angles = Mock()
        cycles = []

        def next_cycle(delay):
            cycles.append(delay)
            if len(cycles) == 30:
                interface.running = False

        interface.running = True
        with patch("classes.gimbal_interface.time.sleep", side_effect=next_cycle):
            interface._query_loop()
        self.assertEqual(interface.query_tracking_status.call_count, 6)
        self.assertEqual(interface.query_gimbal_body_angles.call_count, 10)
        self.assertEqual(interface.query_spatial_fixed_angles.call_count, 30)
        self.assertEqual(cycles, [0.1] * 30)

    def test_binary_commands_preserve_bytes_on_existing_socket(self):
        command = bytes.fromhex("237470504441774c4f4300000000003e006f00094537")
        self.interface.control_socket = Mock()
        with patch("classes.gimbal_interface.socket.socket") as create_socket:
            self.assertTrue(self.interface._send_command(command))
        create_socket.assert_not_called()
        self.interface.control_socket.sendto.assert_called_once_with(
            command, (self.interface.gimbal_ip, self.interface.control_port),
        )

    def test_stop_clears_samples_even_when_worker_is_already_stopped(self):
        self.ingest(BODY, now=10.0)
        self.ingest(ACTIVE, now=10.0)
        self.ingest(SPATIAL, now=10.0)
        self.interface.control_socket = Mock()
        command_socket = self.interface.control_socket
        self.interface.running = False
        self.interface.stop_listening()
        command_socket.close.assert_called_once()
        self.assertIsNone(self.interface.current_angles)
        self.assertIsNone(self.interface.current_tracking_status)
        self.assertIsNone(self.interface.last_tracking_update_time)
        self.assertIsNone(self.interface.last_data_time)
        self.assertEqual(self.interface.last_spatial_packet, "")
        self.assertIsNone(self.interface.get_current_data())
        self.assertIsNone(self.interface.get_tracking_status())


if __name__ == "__main__":
    unittest.main()
