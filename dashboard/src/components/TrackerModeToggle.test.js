import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import TrackerModeToggle from './TrackerModeToggle';
import { endpoints } from '../services/apiEndpoints';
import { apiFetch, apiFetchJson } from '../services/apiClient';

let mockHasScope = () => true;

jest.mock('../services/apiClient', () => ({
  apiFetch: jest.fn(),
  apiFetchJson: jest.fn(),
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: mockHasScope,
  }),
}));

beforeEach(() => {
  apiFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ smart_mode_active: false }),
  });
  apiFetchJson.mockResolvedValue({ status: 'success' });
});

afterEach(() => {
  mockHasScope = () => true;
  jest.clearAllMocks();
});

test('uses typed confirmed smart-mode toggle action', async () => {
  const setSmartModeActive = jest.fn();

  render(
    <TrackerModeToggle
      smartModeActive={false}
      setSmartModeActive={setSmartModeActive}
    />
  );

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith(
      endpoints.status,
      expect.objectContaining({ cache: 'no-store' })
    );
  });

  fireEvent.click(screen.getByRole('checkbox'));

  await waitFor(() => {
    expect(apiFetchJson).toHaveBeenCalledWith(
      endpoints.smartModeToggleAction,
      expect.objectContaining({
        method: 'POST',
        body: expect.any(String),
      })
    );
  });

  const request = JSON.parse(apiFetchJson.mock.calls[0][1].body);
  expect(request).toEqual(expect.objectContaining({
    source: 'dashboard',
    reason: 'toggle_smart_mode',
    confirm: true,
    idempotency_key: expect.stringMatching(/^dashboard-toggle-smart-mode-\d+-[a-z0-9]+$/),
    metadata: { ui: 'tracker_mode_toggle' },
  }));
});

test('disables smart-mode action without actions execute scope', async () => {
  mockHasScope = () => false;
  const setSmartModeActive = jest.fn();

  render(
    <TrackerModeToggle
      smartModeActive={false}
      setSmartModeActive={setSmartModeActive}
    />
  );

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalled();
  });

  const toggle = screen.getByRole('checkbox');
  expect(toggle).toBeDisabled();
  fireEvent.click(toggle);

  expect(apiFetchJson).not.toHaveBeenCalled();
});
