import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
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

afterEach(() => {
  jest.clearAllMocks();
});

test('renders runtime log sessions and filtered entries', async () => {
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
            components: ['backend'],
            claim_boundary: 'Process-local logs only.',
          },
        ],
      }));
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
          },
        ],
      }));
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  render(<LogsPage />);

  expect(await screen.findByText('Backend Runtime Logs')).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getAllByText('pixeagle_demo').length).toBeGreaterThan(0);
  });
  expect(await screen.findByText('Video source unavailable')).toBeInTheDocument();
  expect(screen.getByText(/Backend process logs only/)).toBeInTheDocument();
  expect(apiFetch).toHaveBeenCalledWith(`${endpoints.logSessions}?limit=50`);
});
