import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import LogsPage from './LogsPage';
import { apiFetch } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

jest.mock('../services/apiClient', () => ({
  apiFetch: jest.fn(),
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: (scope) => scope === 'debug:read',
  }),
}));

const jsonResponse = (payload) => ({
  ok: true,
  status: 200,
  json: async () => payload,
});

const installLogsPageFetchMocks = (extra = {}) => {
  apiFetch.mockImplementation((url) => {
    if (url === endpoints.logsStatus) {
      return Promise.resolve(jsonResponse({
        enabled: true,
        active_run_id: 'pixeagle_demo',
        base_dir: '/tmp/pixeagle/logs/runtime',
        active_session_dir: '/tmp/pixeagle/logs/runtime/pixeagle_demo',
        manifest: { run_id: 'pixeagle_demo' },
        claim_boundary: 'Process-local logs only.',
      }));
    }
    if (url === `${endpoints.logSessions}?limit=50`) {
      return Promise.resolve(jsonResponse({
        active_run_id: 'pixeagle_demo',
        sessions: [
          {
            run_id: 'pixeagle_demo',
            active: true,
            created_at: '2026-07-04T12:00:00.000Z',
            modified_at: '2026-07-04T12:01:00.000Z',
            size_bytes: 2048,
            components: ['backend', 'dashboard'],
            claim_boundary: 'Process-local logs only.',
          },
        ],
      }));
    }
    if (extra[url]) {
      return Promise.resolve(extra[url]);
    }
    if (url.startsWith(endpoints.logSessionEntries('pixeagle_demo'))) {
      return Promise.resolve(jsonResponse({
        run_id: 'pixeagle_demo',
        component: 'backend',
        count: 1,
        limit: 200,
        offset: 0,
        entries: [
          {
            ts: '2026-07-04T12:01:00.000Z',
            level: 'ERROR',
            logger: 'classes.video_handler',
            message: 'Video source unavailable',
            line: 42,
            stream: 'combined',
            source: 'launcher-pipe',
            extra: {
              event: 'frontend_error',
              name: 'TypeError',
              route: '/dashboard',
              stack: 'TypeError: failed render',
              context: {
                kind: 'window_error',
              },
            },
          },
        ],
      }));
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });
};

afterEach(() => {
  jest.clearAllMocks();
});

test('renders runtime log sessions and filtered entries', async () => {
  installLogsPageFetchMocks();

  render(<LogsPage />);

  expect(await screen.findByText('Runtime Component Logs')).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getAllByText('pixeagle_demo').length).toBeGreaterThan(0);
  });
  expect(await screen.findByText('Video source unavailable')).toBeInTheDocument();
  expect(screen.getByText(/PixEagle process logs and launcher-captured component output only/)).toBeInTheDocument();
  expect(screen.getByText('dashboard')).toBeInTheDocument();
  expect(screen.getByText('combined')).toBeInTheDocument();
  expect(screen.getByText('launcher-pipe')).toBeInTheDocument();
  expect(screen.getByText('TypeError')).toBeInTheDocument();
  expect(screen.getByText('/dashboard')).toBeInTheDocument();
  expect(screen.getByText('window_error')).toBeInTheDocument();
  expect(screen.getByText('TypeError: failed render')).toBeInTheDocument();
  expect(apiFetch).toHaveBeenCalledWith(`${endpoints.logSessions}?limit=50`);
});

test('downloads selected runtime log evidence bundle', async () => {
  const exportUrl = endpoints.logSessionExport('pixeagle_demo');
  const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  URL.createObjectURL = jest.fn(() => 'blob:pixeagle-runtime-logs');
  URL.revokeObjectURL = jest.fn();
  installLogsPageFetchMocks({
    [exportUrl]: {
      ok: true,
      status: 200,
      headers: {
        get: (name) => (
          name.toLowerCase() === 'content-disposition'
            ? 'attachment; filename="pixeagle_demo-runtime-logs.tar.gz"'
            : ''
        ),
      },
      blob: async () => new Blob(['bundle'], { type: 'application/gzip' }),
    },
  });

  render(<LogsPage />);

  await screen.findByText('Video source unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Download evidence bundle' }));

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith(exportUrl);
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:pixeagle-runtime-logs');
  expect(clickSpy).toHaveBeenCalled();
  clickSpy.mockRestore();
});
