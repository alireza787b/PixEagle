#!/usr/bin/env python3
"""Local ideal-gimbal controls; no aircraft or public camera-control API."""

import argparse
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from classes.aircraft_state import Quaternion, Vector3  # noqa: E402
from tools.gazebo_gimbal_provider import atomic_json  # noqa: E402


class RenderedGimbalGUI:
    def __init__(self, private):
        import tkinter as tk
        from tkinter import ttk
        self.private = private
        self.root = tk.Tk()
        self.root.title('PixEagle · simulated stabilized camera')
        self.root.geometry('600x420')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.state = self.pending = self.timer = None
        self.desired_aim = None
        self.initialized = False
        self.azimuth = tk.DoubleVar(value=0.)
        self.elevation = tk.DoubleVar(value=0.)
        self.distance = tk.StringVar(value='100')
        self.readout = tk.StringVar(value='Waiting for observed camera pose…')
        self.status = tk.StringVar()
        area = ttk.Frame(self.root, padding=20)
        area.pack(fill='both', expand=True)
        area.columnconfigure(1, weight=1)
        ttk.Label(area, text='World-stabilized aim').grid(row=0, column=0, columnspan=3, pady=(0, 12))
        ttk.Label(area, text='Up').grid(row=1, column=0)
        self.up = ttk.Scale(area, from_=90., to=-90., variable=self.elevation,
            orient='vertical', length=170, command=self.aim)
        self.up.grid(row=2, column=0, rowspan=4, padx=(0, 18))
        ttk.Label(area, text='Bearing · North 0° / East +90°').grid(row=1, column=1, columnspan=2)
        self.pan = ttk.Scale(area, from_=-180., to=180., variable=self.azimuth, command=self.aim)
        self.pan.grid(row=2, column=1, columnspan=2, sticky='ew')
        for widget in (self.up, self.pan):
            widget.bind('<ButtonRelease-1>', self.aim)
            widget.bind('<KeyRelease>', self.aim)
        self.horizon = ttk.Button(area, text='Horizon', command=self.horizon_aim)
        self.horizon.grid(row=3, column=1, sticky='w', pady=8)
        self.lock = ttk.Button(area, text='Lock current aim', command=self.lock_aim)
        self.lock.grid(row=4, column=1, sticky='ew', pady=8)
        row = ttk.Frame(area)
        row.grid(row=4, column=2, padx=(10, 0))
        ttk.Label(row, text='Range m').pack(side='left')
        self.range_entry = ttk.Entry(row, textvariable=self.distance, width=7)
        self.range_entry.pack(side='left', padx=5)
        ttk.Label(area, text='Down').grid(row=6, column=0)
        self.lost = ttk.Button(area, text='Simulate loss', command=lambda: self.send('lost'))
        self.lost.grid(row=5, column=1, sticky='ew')
        self.release = ttk.Button(area, text='Clear lock', command=lambda: self.send('release'))
        self.release.grid(row=5, column=2, sticky='ew', padx=(10, 0))
        ttk.Label(area, textvariable=self.readout, justify='center').grid(row=7, column=0, columnspan=3, pady=12)
        ttk.Label(area, textvariable=self.status).grid(row=8, column=0, columnspan=3)
        ttk.Label(area, text='Ideal simulator · synthetic lock · Start / Stop following stays in QGC').grid(
            row=9, column=0, columnspan=3, pady=(12, 0))
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())
        self.refresh()

    def _available(self):
        return (self.state is not None and self.pending is None
                and 0 <= time.monotonic() - self.state['pose']['received_at_monotonic_s'] < .5)

    def send(self, operation, **arguments):
        if not self._available():
            self.status.set('Waiting for fresh camera feedback')
            return
        value = dict(incarnation=self.state['incarnation'], sequence=self.state['control_sequence'] + 1,
                     operation=operation, **arguments)
        atomic_json(self.private / 'operator-command.json', value)
        self.pending = value
        self.status.set('Applying camera input…')

    def aim(self, *_):
        if self.initialized:
            self.desired_aim = self.azimuth.get(), self.elevation.get()

    def horizon_aim(self):
        self.elevation.set(0.)
        self.aim()

    def lock_aim(self):
        try:
            value = float(self.distance.get())
            if not math.isfinite(value) or not .1 <= value <= 10_000.:
                raise ValueError
        except ValueError:
            self.status.set('Use a finite simulated range from 0.1 to 10000 m')
            return
        self.send('lock', range_m=value)

    def refresh(self):
        try:
            value = json.loads((self.private / 'operator-state.json').read_text())
            if self.state is not None and value['incarnation'] != self.state['incarnation']:
                self.pending = None
                self.desired_aim = None
                self.initialized = False
            self.state = value
            if self.pending is not None and value['control_sequence'] >= self.pending['sequence']:
                self.pending = None
                self.status.set('')
            if self.pending is not None and value.get('control_error'):
                self.pending = self.desired_aim = None
                self.status.set('Input rejected; adjust and try again')
            q = value['pose']['camera_to_ned']
            ray = Quaternion(q['w'], q['x'], q['y'], q['z']).rotate(Vector3(1., 0., 0.))
            bearing = math.degrees(math.atan2(ray.y, ray.x))
            elevation = -math.degrees(math.atan2(ray.z, ray.horizontal_magnitude))
            if not self.initialized:
                self.azimuth.set(bearing)
                self.elevation.set(elevation)
                self.initialized = True
            raw = value['angles_deg']
            self.readout.set(f'{value["tracking_state"].replace("_", " ").title()}\n'
                f'Observed bearing {bearing:+.1f}° · elevation {elevation:+.1f}°\n'
                f'Raw Y/P/R {raw[0]:+.1f} / {raw[1]:+.1f} / {raw[2]:+.1f}°')
        except (OSError, ValueError, KeyError, TypeError):
            self.state = None
        available = self._available()
        if available and self.desired_aim is not None:
            azimuth, elevation = self.desired_aim
            self.desired_aim = None
            self.send('aim', azimuth_deg=azimuth, elevation_deg=elevation)
            available = self._available()
        for widget in (self.horizon, self.lock, self.lost, self.release, self.range_entry):
            widget.state(['!disabled'] if available else ['disabled'])
        fresh = (self.state is not None
                 and 0 <= time.monotonic() - self.state['pose']['received_at_monotonic_s'] < .5)
        for widget in (self.pan, self.up):
            widget.state(['!disabled'] if fresh else ['disabled'])
        if not available and self.pending is None:
            self.status.set('Waiting for fresh camera feedback')
        self.timer = self.root.after(100, self.refresh)

    def close(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private', type=Path, required=True)
    args = parser.parse_args()
    RenderedGimbalGUI(args.private).run()


if __name__ == '__main__':
    main()
