#!/usr/bin/env python3
"""Drop deliveries only inside the canonical isolated SITL ownership fixture."""
import argparse
import json
import os
import re
import socket
import time


class ReleaseDropPolicy:
    def __init__(self, count):
        if type(count) is not int or not 0 <= count <= 16:
            raise ValueError('Release drop count must be an integer from 0 to 16')
        self.count = count
        self._token = None
        self._dropped = 0

    def drop(self, *, release, token):
        if not release:
            return False
        if token != self._token:
            self._token, self._dropped = token, 0
        if self._dropped >= self.count:
            return False
        self._dropped += 1
        return True


def require_isolation():
    token = os.environ.get('PIXEAGLE_SITL_OWNED_REQUEST_FAULT', '')
    if re.fullmatch('[a-f0-9]{32}', token) is None or {name for _, name in socket.if_nameindex()} != {'lo'}:
        raise RuntimeError('Ownership fault relay requires its token-owned loopback-only simulator namespace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drop-releases', type=int, required=True)
    args = parser.parse_args()
    policy = ReleaseDropPolicy(args.drop_releases)
    require_isolation()
    import rclpy
    from px4_msgs.msg import OwnedModeRequest

    rclpy.init()
    node = rclpy.create_node('pixeagle_sitl_owned_request_fault')
    destination = node.create_publisher(OwnedModeRequest, '/fmu/in/owned_mode_request', 4)

    def forward(message):
        dropped = policy.drop(release=message.operation == message.OPERATION_RELEASE,
                              token=tuple(message.token))
        print(json.dumps(dict(received_at_monotonic_s=time.monotonic(), operation=message.operation,
            dropped=dropped, source_clock_us=message.source_clock_us, expires_at_us=message.expires_at_us)), flush=True)
        if not dropped:
            destination.publish(message)

    subscription = node.create_subscription(OwnedModeRequest, '/pixeagle_sitl/owned_mode_request', forward, 4)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
