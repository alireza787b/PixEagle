import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import LogsPage from './LogsPage';
import { apiFetch } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

let mockCanReadLogs = true;

jest.mock('../services/apiClient', () => ({
  apiFetch: jest.fn(),
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: (scope) => mockCanReadLogs && scope === 'debug:read',
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
      const value = typeof extra[url] === 'function' ? extra[url](url) : extra[url];
      return Promise.resolve(value);
    }
    if (url.startsWith(endpoints.logSessionEntries('pixeagle_demo'))) {
      return Promise.resolve(jsonResponse({
        run_id: 'pixeagle_demo',
        component: 'backend',
        count: 1,
        limit: 200,
        offset: 0,
        next_offset: 1,
        tail: false,
        matched_total: 1,
        has_more: false,
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
  mockCanReadLogs = true;
  jest.clearAllMocks();
  jest.useRealTimers();
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
        get: (name) => {
          const headers = {
            'content-disposition': 'attachment; filename="pixeagle_demo-runtime-logs.tar.gz"',
            'x-pixeagle-run-id': 'pixeagle_demo',
            'x-pixeagle-log-export-sha256': 'abc123def456',
            'x-pixeagle-log-export-size': '123',
            'x-pixeagle-claim-boundary': 'Process-local logs only; not flight proof.',
          };
          return headers[name.toLowerCase()] || '';
        },
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
  expect(await screen.findByText('Evidence bundle downloaded')).toBeInTheDocument();
  expect(screen.getByText('pixeagle_demo-runtime-logs.tar.gz')).toBeInTheDocument();
  expect(screen.getByText('123 B')).toBeInTheDocument();
  expect(screen.getByText('abc123def456')).toBeInTheDocument();
  expect(screen.getByText('Process-local logs only; not flight proof.')).toBeInTheDocument();
  clickSpy.mockRestore();
});

test('enables live tail and polls from returned cursor', async () => {
  jest.useFakeTimers();
  const entriesBase = endpoints.logSessionEntries('pixeagle_demo');
  const initialTailUrl = `${entriesBase}?component=backend&limit=200&offset=0&tail=true`;
  const pollUrl = `${entriesBase}?component=backend&limit=200&offset=3`;
  installLogsPageFetchMocks({
    [initialTailUrl]: jsonResponse({
      run_id: 'pixeagle_demo',
      component: 'backend',
      count: 1,
      limit: 200,
      offset: 2,
      next_offset: 3,
      tail: true,
      matched_total: 3,
      has_more: true,
      entries: [
        {
          ts: '2026-07-04T12:01:03.000Z',
          level: 'INFO',
          logger: 'classes.runtime_logging',
          message: 'tail newest',
          line: 7,
        },
      ],
    }),
    [pollUrl]: jsonResponse({
      run_id: 'pixeagle_demo',
      component: 'backend',
      count: 1,
      limit: 200,
      offset: 3,
      next_offset: 4,
      tail: false,
      matched_total: 4,
      has_more: false,
      entries: [
        {
          ts: '2026-07-04T12:01:04.000Z',
          level: 'WARNING',
          logger: 'classes.runtime_logging',
          message: 'tail appended',
          line: 8,
        },
      ],
    }),
  });

  render(<LogsPage />);

  await screen.findByText('Video source unavailable');
  fireEvent.click(screen.getByLabelText('Live tail'));

  expect(await screen.findByText('tail newest')).toBeInTheDocument();
  await act(async () => {
    jest.advanceTimersByTime(2000);
  });

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith(pollUrl);
  });
  expect(await screen.findByText('tail appended')).toBeInTheDocument();
  expect(screen.getByText('Next offset 4')).toBeInTheDocument();
});

test('disables live tail when runtime logs are not readable', async () => {
  mockCanReadLogs = false;
  installLogsPageFetchMocks();

  render(<LogsPage />);

  expect(await screen.findByText(/Runtime logs require debug read access/)).toBeInTheDocument();
  expect(screen.getByLabelText('Live tail')).toBeDisabled();
  expect(apiFetch).not.toHaveBeenCalledWith(endpoints.logsStatus);
});

test('ignores stale live-tail poll responses after disabling live tail', async () => {
  jest.useFakeTimers();
  const entriesBase = endpoints.logSessionEntries('pixeagle_demo');
  const initialTailUrl = `${entriesBase}?component=backend&limit=200&offset=0&tail=true`;
  const pollUrl = `${entriesBase}?component=backend&limit=200&offset=3`;
  let resolvePoll;
  const pendingPoll = new Promise((resolve) => {
    resolvePoll = resolve;
  });
  installLogsPageFetchMocks({
    [initialTailUrl]: jsonResponse({
      run_id: 'pixeagle_demo',
      component: 'backend',
      count: 1,
      limit: 200,
      offset: 2,
      next_offset: 3,
      tail: true,
      matched_total: 3,
      has_more: true,
      entries: [
        {
          ts: '2026-07-04T12:01:03.000Z',
          level: 'INFO',
          logger: 'classes.runtime_logging',
          message: 'tail newest',
          line: 7,
        },
      ],
    }),
    [pollUrl]: () => pendingPoll,
  });

  render(<LogsPage />);

  await screen.findByText('Video source unavailable');
  fireEvent.click(screen.getByLabelText('Live tail'));
  expect(await screen.findByText('tail newest')).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(2000);
  });
  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith(pollUrl);
  });

  fireEvent.click(screen.getByLabelText('Live tail'));
  await act(async () => {
    resolvePoll(jsonResponse({
      run_id: 'pixeagle_demo',
      component: 'backend',
      count: 1,
      limit: 200,
      offset: 3,
      next_offset: 4,
      tail: false,
      matched_total: 4,
      has_more: false,
      entries: [
        {
          ts: '2026-07-04T12:01:04.000Z',
          level: 'WARNING',
          logger: 'classes.runtime_logging',
          message: 'stale appended',
          line: 8,
        },
      ],
    }));
  });

  await waitFor(() => {
    expect(screen.getByText('Video source unavailable')).toBeInTheDocument();
  });
  expect(screen.queryByText('stale appended')).not.toBeInTheDocument();
});
