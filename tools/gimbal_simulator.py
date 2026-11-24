#!/usr/bin/env python3
"""Local Topotek angle/status stimulus; not a mechanical or aircraft simulator."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import logging
import math
from pathlib import Path
import socket
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from classes.gimbal_control import sip_frame  # noqa: E402
from classes.gimbal_geometry import body_bearing_to_angles, require_finite_body_angles, resolve_angle_geometry, resolve_mount_type  # noqa: E402
from classes.gimbal_types import TrackingState as SimulatedTrackingState  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimulatorConfig:
    listen_host: str = '127.0.0.1'
    listen_port: int = 9003
    broadcast_host: str = '127.0.0.1'
    broadcast_port: int = 9004
    angle_period_s: float = .1
    status_period_s: float = .5

    def __post_init__(self):
        if type(self.listen_port) is not int or not 0 <= self.listen_port <= 65535:
            raise ValueError('Simulator listen port must be an integer from 0 to 65535')
        if type(self.broadcast_port) is not int or not 1 <= self.broadcast_port <= 65535:
            raise ValueError('Simulator destination port must be an integer from 1 to 65535')
        for period in (self.angle_period_s, self.status_period_s):
            if type(period) not in (int, float) or not math.isfinite(period) or period < .01:
                raise ValueError('Simulator sample periods must be finite and at least 10 ms')


def angle_hex(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 180:
        raise ValueError('Angle must be finite and within the normalized protocol range')
    return f'{int(round(value * 100)) & 0xffff:04X}'


class GimbalSimulator:
    """One UDP worker, independent angle/status feeds and explicit lock stimulus."""
    def __init__(self, config=None):
        self.config = config or SimulatorConfig()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._socket = self._thread = None
        self._angles = (0., 0., 0.)
        self._tracking = SimulatedTrackingState.DISABLED
        self._freeze_angles = self._freeze_status = False

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    @property
    def address(self):
        return self._socket.getsockname() if self._socket is not None else None

    def set_gimbal_angles(self, yaw, pitch, roll):
        values = require_finite_body_angles((yaw, pitch, roll))
        for value in values:
            angle_hex(value)
        with self._lock:
            self._angles = values

    def set_tracking_state(self, state):
        if not isinstance(state, SimulatedTrackingState):
            raise ValueError('Use a normalized tracking state')
        with self._lock:
            self._tracking = state

    def freeze(self, *, angles=False, status=False):
        if type(angles) is not bool or type(status) is not bool:
            raise ValueError('Freeze flags must be boolean')
        with self._lock:
            self._freeze_angles, self._freeze_status = angles, status

    def get_state(self):
        with self._lock:
            return dict(angles=dict(zip(('yaw', 'pitch', 'roll'), self._angles)),
                tracking_state=self._tracking.name, freeze_angles=self._freeze_angles,
                freeze_status=self._freeze_status)

    def _packets(self):
        with self._lock:
            angle = None if self._freeze_angles else sip_frame(
                ('#tpGPCrGAC' + ''.join(angle_hex(value) for value in self._angles)).encode('ascii'))
            status = None if self._freeze_status else sip_frame(f'#TPDP2rTRC0{self._tracking.value}'.encode('ascii'))
            return angle, status

    def _process_command(self, packet):
        if isinstance(packet, str):
            try:
                packet = packet.encode('ascii')
            except UnicodeError:
                return None
        if not isinstance(packet, bytes) or len(packet) != 14 or sip_frame(packet[:-2]) != packet:
            return None
        if packet[:-2] == b'#TPPG2rGAC00':
            return self._packets()[0]
        if packet[:-2] == b'#TPPD2rTRC00':
            return self._packets()[1]
        # No spatial-angle, motor, selection or calibration authority is invented.
        return None

    def start(self):
        if self.running:
            return
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError('Previous simulator worker has not stopped')
        stream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            stream.bind((self.config.listen_host, self.config.listen_port))
            stream.settimeout(.02)
        except BaseException:
            stream.close()
            raise
        self._socket = stream
        self.set_tracking_state(SimulatedTrackingState.DISABLED)
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, args=(stream,), name='topotek-stimulus', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        worker = self._thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.)
            if worker.is_alive():
                raise RuntimeError('Simulator worker did not stop')
        self._thread = self._socket = None

    def _serve(self, stream):
        angle_due = status_due = time.monotonic()
        destination = (self.config.broadcast_host, self.config.broadcast_port)
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                angle, status = self._packets()
                if now >= angle_due:
                    if angle is not None:
                        stream.sendto(angle, destination)
                    angle_due = now + self.config.angle_period_s
                if now >= status_due:
                    if status is not None:
                        stream.sendto(status, destination)
                    status_due = now + self.config.status_period_s
                try:
                    packet, address = stream.recvfrom(4096)
                    response = self._process_command(packet)
                    if response is not None:
                        stream.sendto(response, address)
                except socket.timeout:
                    pass
        except OSError:
            if not self._stop.is_set():
                logger.exception('Simulator UDP feed failed')
        finally:
            self._stop.set()
            stream.close()


class GimbalSimulatorGUI:
    def __init__(self, *, geometry, mount, config=None):
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError as error:
            raise RuntimeError('GUI requires Tk. On Ubuntu install python3-tk.') from error
        self.root = tk.Tk()
        self.root.title('PixEagle · Topotek input test')
        self.root.geometry('560x450')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.simulator = GimbalSimulator(config)
        self.geometry = geometry
        self.azimuth = tk.DoubleVar(value=0.)
        self.elevation = tk.DoubleVar(value=0.)
        self.freeze_angles = tk.BooleanVar(value=False)
        self.freeze_status = tk.BooleanVar(value=False)
        self.tracking = tk.StringVar(value='DISABLED')
        self.readout = tk.StringVar()
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=f'{mount.title()} mount · simulated angle input').grid(row=0, column=0, columnspan=3)
        ttk.Label(frame, text='Up').grid(row=1, column=0)
        ttk.Scale(frame, from_=90, to=-90, variable=self.elevation, orient='vertical',
            length=160, command=self.aim).grid(row=2, column=0, rowspan=3, padx=(0, 16))
        ttk.Label(frame, text='Left / Right').grid(row=1, column=1)
        ttk.Scale(frame, from_=-180, to=180, variable=self.azimuth, length=320,
            command=self.aim).grid(row=2, column=1, columnspan=2, sticky='ew')
        ttk.Button(frame, text='Center', command=self.reset).grid(row=3, column=1, sticky='w')
        ttk.Label(frame, text='Down').grid(row=5, column=0)
        states = ttk.Combobox(frame, textvariable=self.tracking, state='readonly', width=20,
            values=('DISABLED', 'TARGET_SELECTION', 'TRACKING_ACTIVE', 'TARGET_LOST'))
        states.grid(row=4, column=1, sticky='w')
        states.bind('<<ComboboxSelected>>', lambda _: self.simulator.set_tracking_state(SimulatedTrackingState[self.tracking.get()]))
        ttk.Checkbutton(frame, text='Freeze angles', variable=self.freeze_angles, command=self.freeze).grid(row=6, column=0, columnspan=2, sticky='w')
        ttk.Checkbutton(frame, text='Freeze lock status', variable=self.freeze_status, command=self.freeze).grid(row=7, column=0, columnspan=2, sticky='w')
        ttk.Label(frame, textvariable=self.readout).grid(row=8, column=0, columnspan=3, pady=10)
        ttk.Label(frame, text='Protocol stimulus only · no Gazebo or aircraft control').grid(row=9, column=0, columnspan=3)
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())
        self.reset()
        try:
            self.simulator.start()
        except BaseException:
            self.root.destroy()
            raise

    def aim(self, *_):
        angles = body_bearing_to_angles(self.azimuth.get(), -self.elevation.get(), self.geometry)
        self.simulator.set_gimbal_angles(*angles)
        self.readout.set(f'Right {self.azimuth.get():+.1f}°   Up {self.elevation.get():+.1f}°\n'
                         f'Raw Y/P/R: {angles[0]:+.1f} / {angles[1]:+.1f} / {angles[2]:+.1f}°')

    def reset(self):
        self.azimuth.set(0.)
        self.elevation.set(0.)
        self.aim()

    def freeze(self):
        self.simulator.freeze(angles=self.freeze_angles.get(), status=self.freeze_status.get())

    def close(self):
        self.simulator.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Read the existing GimbalTracker installation; never writes it')
    args = parser.parse_args()
    camera = {}
    if args.config is not None:
        import yaml
        camera = yaml.safe_load(args.config.read_text()).get('GimbalTracker', {})
    mount = resolve_mount_type(camera, {}, {}, allowed=('HORIZONTAL', 'VERTICAL'))
    gui = GimbalSimulatorGUI(geometry=resolve_angle_geometry(camera, mount), mount=mount)
    try:
        gui.run()
    finally:
        gui.simulator.stop()


if __name__ == '__main__':
    main()
