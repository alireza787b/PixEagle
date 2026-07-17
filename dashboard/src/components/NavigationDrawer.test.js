import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NavigationDrawer from './NavigationDrawer';
import { endpoints } from '../services/apiEndpoints';
import { apiFetch } from '../services/apiClient';

let mockIsFollowing = false;

jest.mock('../services/apiClient', () => ({
  apiFetch: jest.fn(),
}));

jest.mock('../hooks/useStatuses', () => ({
  useTrackerStatus: () => ({
    navLabel: 'Tracker idle',
    color: 'default',
    usableForFollowing: false,
  }),
  useFollowerStatus: () => mockIsFollowing,
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: () => true,
  }),
}));

jest.mock('./QuitButton', () => () => <button type="button">Quit</button>);

const response = (body, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: jest.fn(() => Promise.resolve(body)),
});

const renderDrawer = () => render(
  <MemoryRouter initialEntries={['/dashboard']}>
    <NavigationDrawer mobileOpen={false} handleDrawerToggle={jest.fn()} />
  </MemoryRouter>
);

beforeEach(() => {
  apiFetch.mockReset();
  mockIsFollowing = false;
});

test('shows an unknown following state instead of optimistic standby', () => {
  mockIsFollowing = undefined;
  apiFetch.mockImplementation(() => new Promise(() => {}));

  renderDrawer();

  expect(screen.getAllByText('Status unknown').length).toBeGreaterThan(0);
  expect(screen.queryAllByText('Standby')).toHaveLength(0);
});

test('loads typed system about metadata in the version dialog', async () => {
  apiFetch.mockResolvedValueOnce(response({
    schema_version: 1,
    source: 'pixeagle_system_about',
    version: '9.8.7',
    repository: {
      name: 'PixEagle',
      url: 'https://github.com/alireza787b/PixEagle',
    },
    git: {
      commit: 'abc1234',
      branch: 'codex/about',
      date: '2026-07-05T12:34:56Z',
      dirty: true,
    },
    backend: {
      status: 'running',
      restart_pending: false,
    },
    runtime: {
      uptime_seconds: 3661,
      run_id: 'pixeagle_20260705T120000Z_123456',
    },
    update: {
      supported: false,
      state: 'not_checked',
      available: null,
      reason: 'Runtime About does not fetch update metadata.',
    },
    claim_boundary: 'PixEagle process-local version metadata only.',
  }));

  renderDrawer();

  expect((await screen.findAllByText('v9.8.7')).length).toBeGreaterThan(0);
  expect(screen.getAllByText('abc1234').length).toBeGreaterThan(0);
  expect(apiFetch).toHaveBeenCalledWith(endpoints.systemAbout);

  fireEvent.click(screen.getAllByLabelText('About PixEagle')[0]);

  expect(screen.getByText('About PixEagle')).toBeInTheDocument();
  expect(screen.getByText('codex/about')).toBeInTheDocument();
  expect(screen.getByText('Present')).toBeInTheDocument();
  expect(screen.getByText('1h 1m')).toBeInTheDocument();
  expect(screen.getByText('Not checked')).toBeInTheDocument();
  expect(screen.getByText('PixEagle process-local version metadata only.')).toBeInTheDocument();
});

test('falls back to legacy system config only for missing typed route', async () => {
  apiFetch
    .mockResolvedValueOnce(response({ error: 'missing' }, 404))
    .mockResolvedValueOnce(response({
      success: true,
      config: {
        version: '3.2.1',
        git: {
          commit: 'legacy1',
          branch: 'legacy',
          date: '2026-07-04',
        },
      },
    }));

  renderDrawer();

  await waitFor(() => expect(screen.getAllByText('v3.2.1').length).toBeGreaterThan(0));
  expect(apiFetch).toHaveBeenNthCalledWith(1, endpoints.systemAbout);
  expect(apiFetch).toHaveBeenNthCalledWith(2, endpoints.systemConfig);
});

test('does not fall back to legacy config when system about is forbidden', async () => {
  const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  apiFetch.mockResolvedValueOnce(response({ error: 'forbidden' }, 403));

  renderDrawer();

  await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  expect(apiFetch).toHaveBeenCalledWith(endpoints.systemAbout);
  expect(apiFetch).not.toHaveBeenCalledWith(endpoints.systemConfig);
  expect(screen.queryByLabelText('About PixEagle')).not.toBeInTheDocument();

  consoleSpy.mockRestore();
});

test('does not call unchecked update metadata current', async () => {
  apiFetch.mockResolvedValueOnce(response({
    schema_version: 1,
    source: 'pixeagle_system_about',
    version: '9.8.8',
    repository: {
      name: 'PixEagle',
      url: 'https://github.com/alireza787b/PixEagle',
    },
    git: {
      commit: 'def5678',
      branch: 'codex/about-long-branch-name-that-can-wrap',
      date: '2026-07-06T12:34:56Z',
      dirty: false,
    },
    backend: {
      status: 'running',
      restart_pending: false,
    },
    runtime: {
      uptime_seconds: 30,
      run_id: 'pixeagle_20260706T120000Z_abcdef',
    },
    update: {
      supported: false,
      state: 'not_checked',
      available: false,
      checked_at: null,
      reason: 'Update checks are not implemented by the read-only About route.',
    },
    claim_boundary: 'PixEagle process-local version metadata only.',
  }));

  renderDrawer();

  expect((await screen.findAllByText('v9.8.8')).length).toBeGreaterThan(0);
  fireEvent.click(screen.getAllByLabelText('About PixEagle')[0]);

  expect(screen.getByText('Not checked')).toBeInTheDocument();
  expect(screen.queryByText('Current')).not.toBeInTheDocument();
  expect(screen.queryByText('No update found')).not.toBeInTheDocument();
});
