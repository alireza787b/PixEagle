import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import SettingsPage from './SettingsPage';
import { apiFetchJson } from '../services/apiClient';

jest.mock('react-router-dom', () => ({
  useBlocker: () => ({ state: 'unblocked' }),
  useBeforeUnload: jest.fn(),
}));
jest.mock('../hooks/useConfig', () => ({
  useConfigSchema: () => ({
    schema: { sections: {
      VideoSource: { display_name: 'Video source', parameters: { CAPTURE_FPS: { type: 'integer', min: 1, max: 60, unit: 'FPS' } } },
      Streaming: { display_name: 'Streaming', parameters: { STREAM_FPS: { type: 'integer', min: 1, max: 60, unit: 'FPS' } } },
    } },
  }),
}));
jest.mock('../hooks/useDefaultsSync', () => ({ useDefaultsSync: () => ({}) }));
jest.mock('../context/PendingRestartContext', () => ({
  usePendingRestart: () => ({ refreshRuntimeStatus: async () => ({ pending_changes: [] }) }),
}));
jest.mock('../services/apiClient', () => ({ apiFetchJson: jest.fn() }));
jest.mock('../components/config/ExportDialog', () => () => null);
jest.mock('../components/config/SyncWithDefaultsDialog', () => () => null);

const config = { VideoSource: { CAPTURE_FPS: 30 }, Streaming: { STREAM_FPS: 20 } };

function setup() {
  let current = config;
  let revision = 'original';
  apiFetchJson.mockReset();
  apiFetchJson.mockImplementation(async (url, options) => {
    if (url.endsWith('/config/editor')) return { config: current, revision, writable: true };
    if (url.endsWith('/integration/config')) return {};
    if (!url.endsWith('/actions/config-save')) throw new Error(`Unexpected request ${url}`);
    const body = JSON.parse(options.body);
    const changes = body.edits.map(({ path, value }) => ({
      path, old_value: current[path[0]][path[1]], new_value: value, kind: 'changed', reload_tier: 'immediate',
    }));
    if (body.dry_run) return { accepted: true, result: { preview_token: 'review-token', changes } };
    current = Object.fromEntries(Object.entries(current).map(([key, values]) => [key, {
      ...values, ...Object.fromEntries(body.edits.filter((edit) => edit.path[0] === key).map((edit) => [edit.path[1], edit.value])),
    }]));
    revision = 'saved';
    return { accepted: true, executed: true, result: { revision, backup_id: 'backup', changes } };
  });
  render(<SettingsPage />);
}

const writes = () => apiFetchJson.mock.calls.filter(([, options]) => options?.method === 'POST');

test('draft survives section switches and saves only after one reviewed batch', async () => {
  setup();
  const capture = await screen.findByRole('textbox', { name: 'Capture Fps' });
  fireEvent.change(capture, { target: { value: '24' } });
  fireEvent.blur(capture);
  fireEvent.click(screen.getByRole('button', { name: 'Streaming' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Stream Fps' }), { target: { value: '12' } });
  fireEvent.click(screen.getByRole('button', { name: 'Video source' }));
  expect(screen.getByRole('textbox', { name: 'Capture Fps' })).toHaveValue('24');
  expect(writes()).toHaveLength(0);

  fireEvent.click(screen.getByRole('button', { name: 'Review changes (2)' }));
  const review = await screen.findByRole('dialog', { name: 'Review changes' });
  expect(within(review).getByText('24 FPS')).toBeInTheDocument();
  expect(within(review).getByText('12 FPS')).toBeInTheDocument();
  expect(JSON.parse(writes()[0][1].body)).toMatchObject({ dry_run: true });
  fireEvent.click(within(review).getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(screen.getByText('Saved and verified.')).toBeInTheDocument());
  const save = JSON.parse(writes()[1][1].body);
  expect(save).toMatchObject({ confirm: true, preview_token: 'review-token' });
  expect(save.edits).toHaveLength(2);
  expect(await screen.findByRole('button', { name: 'Undo last save' })).toBeEnabled();
});

test('an invalid edit remains visible without sending a mutation', async () => {
  setup();
  const capture = await screen.findByRole('textbox', { name: 'Capture Fps' });
  fireEvent.change(capture, { target: { value: '99' } });
  expect(capture).toHaveValue('99');
  expect(screen.getByText('Maximum 60')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Review changes (1)' })).toBeDisabled();
  expect(writes()).toHaveLength(0);
});
