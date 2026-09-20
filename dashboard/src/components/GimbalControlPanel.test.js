import { fireEvent, render, screen } from '@testing-library/react';
import GimbalControlPanel from './GimbalControlPanel';

const control = {
  enabled: true,
  status: { connected: true, tracking_state: 'ready', capabilities: ['select', 'pan', 'tilt', 'zoom', 'home', 'cancel', 'stop'] },
  canOperate: () => true,
  execute: jest.fn().mockResolvedValue({ status: 'success' }),
};
beforeEach(() => control.execute.mockResolvedValue({ status: 'success' }));

test('camera modes use provider status and remain hidden without the capability', () => {
  const { rerender } = render(<GimbalControlPanel control={control} />);
  expect(screen.queryByRole('group', { name: 'Camera tracking mode' })).not.toBeInTheDocument();
  const modes = { ...control, status: { ...control.status, capabilities: ['set_mode'], selection_mode: 'classic' } };
  rerender(<GimbalControlPanel control={modes} />);
  const smart = screen.getByRole('button', { name: 'Smart Tracker' });
  fireEvent.click(smart);
  expect(control.execute).toHaveBeenLastCalledWith('set_mode', { selection_mode: 'smart' });
  expect(smart).toHaveAttribute('aria-pressed', 'false');
  rerender(<GimbalControlPanel control={{ ...modes, status: { ...modes.status, selection_mode: 'smart' } }} />);
  expect(screen.getByRole('button', { name: 'Smart Tracker' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.queryByText(/Detection and tracking run on the camera/)).not.toBeInTheDocument();
});

test('smart mode can be prepared again after cancel and obeys the control guard', () => {
  const modes = { ...control, status: { ...control.status, capabilities: ['set_mode'], selection_mode: 'smart', tracking_state: 'disabled' } };
  const { rerender } = render(<GimbalControlPanel control={modes} />);
  const smart = screen.getByRole('button', { name: 'Smart Tracker' });
  expect(smart).toBeEnabled();
  fireEvent.click(smart);
  expect(control.execute).toHaveBeenLastCalledWith('set_mode', { selection_mode: 'smart' });
  expect(screen.queryByText(/Choose Smart Tracker to show camera detections/)).not.toBeInTheDocument();
  rerender(<GimbalControlPanel control={{ ...modes, canOperate: () => false }} />);
  expect(screen.getByRole('button', { name: 'Classic Tracker' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Smart Tracker' })).toBeDisabled();
});
afterEach(() => jest.clearAllMocks());

test('disabled integration contributes no interface', () => {
  const { container } = render(<GimbalControlPanel control={{ enabled: false }} />);
  expect(container).toBeEmptyDOMElement();
});

test('camera buttons send one bounded operation per click', () => {
  render(<GimbalControlPanel control={control} />);
  fireEvent.click(screen.getByRole('button', { name: 'Tilt up' }));
  expect(control.execute).toHaveBeenCalledWith('tilt', { direction: -1 });
  expect(control.execute).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Ready')).toBeInTheDocument();
});

test('following explains the block and retains camera stop', () => {
  render(<GimbalControlPanel control={{
    ...control,
    status: { ...control.status, following_active: true },
    canOperate: operation => operation === 'stop',
  }} />);
  expect(screen.getByRole('button', { name: 'Cancel target' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Pan left' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Stop camera' })).toBeEnabled();
  expect(screen.getByText(/Stop following before selecting/)).toBeInTheDocument();
});


test('roll controls appear only with the capability and send signed directions', () => {
  const { rerender } = render(<GimbalControlPanel control={control} />);
  expect(screen.queryByRole('button', { name: 'Roll −' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Roll +' })).not.toBeInTheDocument();
  rerender(<GimbalControlPanel control={{
    ...control,
    status: { ...control.status, capabilities: [...control.status.capabilities, 'roll'] },
  }} />);
  fireEvent.click(screen.getByRole('button', { name: 'Roll −' }));
  fireEvent.click(screen.getByRole('button', { name: 'Roll +' }));
  expect(control.execute).toHaveBeenNthCalledWith(1, 'roll', { direction: -1 });
  expect(control.execute).toHaveBeenNthCalledWith(2, 'roll', { direction: 1 });
  expect(control.execute).toHaveBeenCalledTimes(2);
});


test.each([
  ['target_selection', 'Ready'], ['tracking_active', 'Tracking'],
  ['target_lost', 'Target lost'], ['disabled', 'Disabled'],
  ['unsupported', 'Unsupported'], ['unknown', 'Unknown'],
])('presents camera state %s as %s', (tracking_state, label) => {
  render(<GimbalControlPanel control={{ ...control, status: { ...control.status, tracking_state } }} />);
  expect(screen.getByText(label)).toBeInTheDocument();
});

test.each([
  ['camera_unavailable', 'Camera unavailable'],
  ['stop_following_first', 'Stop following first'],
  ['tracking_unsupported', 'Tracking unsupported'],
])('presents camera reason %s as %s', (reason, label) => {
  render(<GimbalControlPanel control={{ ...control, status: { ...control.status, reason } }} />);
  expect(screen.getByRole('alert')).toHaveTextContent(label);
});

const motionSettings = {
  min_speed_deg_s: 1, max_speed_deg_s: 30,
  min_duration_ms: 100, max_duration_ms: 1000,
  default_speed_deg_s: 10, default_duration_ms: 250,
  presets: [
    { name: 'fine', label: 'Fine', speed_deg_s: 5, duration_ms: 150 },
    { name: 'normal', label: 'Normal', speed_deg_s: 10, duration_ms: 250 },
    { name: 'fast', label: 'Fast', speed_deg_s: 20, duration_ms: 500 },
  ],
};
const motionControl = () => ({
  ...control,
  status: { ...control.status, capabilities: [...control.status.capabilities, 'roll'], motion_settings: motionSettings },
});
const chooseMovement = value => fireEvent.change(screen.getByRole('combobox', { name: 'Movement' }), { target: { value } });

test('movement settings are hidden unless offered by the provider', () => {
  render(<GimbalControlPanel control={control} />);
  expect(screen.queryByRole('combobox', { name: 'Movement' })).not.toBeInTheDocument();
});

test('Normal starts from provider defaults and presets apply only to movement commands', () => {
  render(<GimbalControlPanel control={motionControl()} />);
  expect(screen.getByRole('combobox', { name: 'Movement' })).toHaveValue('normal');
  fireEvent.click(screen.getByRole('button', { name: 'Pan left' }));
  expect(control.execute).toHaveBeenLastCalledWith('pan', { direction: -1, speed_deg_s: 10, duration_ms: 250 });
  chooseMovement('fast');
  fireEvent.click(screen.getByRole('button', { name: 'Roll +' }));
  expect(control.execute).toHaveBeenLastCalledWith('roll', { direction: 1, speed_deg_s: 20, duration_ms: 500 });
  chooseMovement('fine');
  fireEvent.click(screen.getByRole('button', { name: 'Tilt up' }));
  expect(control.execute).toHaveBeenLastCalledWith('tilt', { direction: -1, speed_deg_s: 5, duration_ms: 150 });
  fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
  expect(control.execute).toHaveBeenLastCalledWith('zoom', { direction: 1 });
  fireEvent.click(screen.getByRole('button', { name: 'Stop camera' }));
  expect(control.execute).toHaveBeenLastCalledWith('stop', {});
});

test('Adjust edits stay local until Apply and show estimated pulse movement', async () => {
  render(<GimbalControlPanel control={motionControl()} />);
  chooseMovement('adjust');
  expect(screen.getByRole('dialog', { name: 'Adjust camera movement' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Speed (°/s)' }), { target: { value: '30' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Pulse duration (ms)' }), { target: { value: '1000' } });
  expect(screen.getByText(/Estimated movement: 30° per press/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  await screen.findByRole('combobox', { name: 'Movement' });
  expect(control.execute).not.toHaveBeenCalled();
  expect(screen.getByRole('combobox', { name: 'Movement' })).toHaveValue('custom');
  fireEvent.click(screen.getByRole('button', { name: 'Pan right' }));
  expect(control.execute).toHaveBeenLastCalledWith('pan', { direction: 1, speed_deg_s: 30, duration_ms: 1000 });
});

test('Cancel discards draft values without commanding the camera', async () => {
  render(<GimbalControlPanel control={motionControl()} />);
  chooseMovement('fine');
  chooseMovement('adjust');
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Speed (°/s)' }), { target: { value: '30' } });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }));
  await screen.findByRole('combobox', { name: 'Movement' });
  expect(control.execute).not.toHaveBeenCalled();
  expect(screen.getByRole('combobox', { name: 'Movement' })).toHaveValue('fine');
  fireEvent.click(screen.getByRole('button', { name: 'Pan right' }));
  expect(control.execute).toHaveBeenLastCalledWith('pan', { direction: 1, speed_deg_s: 5, duration_ms: 150 });
});

test.each([
  ['Speed (°/s)', '0'], ['Speed (°/s)', '31'], ['Speed (°/s)', '1.5'], ['Speed (°/s)', ''],
  ['Pulse duration (ms)', '99'], ['Pulse duration (ms)', '1001'], ['Pulse duration (ms)', '250.5'], ['Pulse duration (ms)', ''],
])('invalid %s value %s blocks Apply', (name, value) => {
  render(<GimbalControlPanel control={motionControl()} />);
  chooseMovement('adjust');
  fireEvent.change(screen.getByRole('spinbutton', { name }), { target: { value } });
  expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  expect(screen.getByRole('spinbutton', { name })).toHaveAttribute('aria-invalid', 'true');
  expect(control.execute).not.toHaveBeenCalled();
});

test('Reset restores advertised defaults and limits follow the provider', async () => {
  const alternate = {
    ...motionControl(), status: { ...motionControl().status, motion_settings: {
      ...motionSettings, max_speed_deg_s: 15, default_speed_deg_s: 8, default_duration_ms: 200,
    } },
  };
  render(<GimbalControlPanel control={alternate} />);
  chooseMovement('adjust');
  expect(screen.getByRole('spinbutton', { name: 'Speed (°/s)' })).toHaveAttribute('max', '15');
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Speed (°/s)' }), { target: { value: '16' } });
  expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Reset to Normal' }));
  expect(screen.getByRole('spinbutton', { name: 'Speed (°/s)' })).toHaveValue(8);
  expect(screen.getByRole('spinbutton', { name: 'Pulse duration (ms)' })).toHaveValue(200);
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  await screen.findByRole('combobox', { name: 'Movement' });
  fireEvent.click(screen.getByRole('button', { name: 'Pan right' }));
  expect(control.execute).toHaveBeenLastCalledWith('pan', { direction: 1, speed_deg_s: 8, duration_ms: 200 });
});

test('polls retain the session choice but provider/settings changes and disable reset it', () => {
  const initial = motionControl();
  const { rerender } = render(<GimbalControlPanel control={initial} />);
  chooseMovement('fast');
  rerender(<GimbalControlPanel control={{ ...initial, status: JSON.parse(JSON.stringify(initial.status)) }} />);
  expect(screen.getByRole('combobox', { name: 'Movement' })).toHaveValue('fast');
  rerender(<GimbalControlPanel control={{ ...initial, status: { ...initial.status, provider: 'other' } }} />);
  expect(screen.getByRole('combobox', { name: 'Movement' })).toHaveValue('normal');
  chooseMovement('fast');
  rerender(<GimbalControlPanel control={{ ...initial, status: { ...initial.status, motion_settings: { ...motionSettings, max_duration_ms: 900 } } }} />);
  expect(screen.getByRole('combobox', { name: 'Movement' })).toHaveValue('normal');
  chooseMovement('fast');
  rerender(<GimbalControlPanel control={{ enabled: false }} />);
  rerender(<GimbalControlPanel control={initial} />);
  expect(screen.getByRole('combobox', { name: 'Movement' })).toHaveValue('normal');
});
