import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SoftwareUpdatePage from './SoftwareUpdatePage';
import { endpoints } from '../services/apiEndpoints';
import { apiFetchJson } from '../services/apiClient';

jest.mock('../services/apiClient', () => ({ apiFetchJson: jest.fn() }));
const release = {
  installed: '1.0.0', state: 'available', release: 'v1.1.0', commit: '1'.repeat(40),
  review: 'a'.repeat(64), changes: [], checked: 1700000000,
};
const mount = () => render(<MemoryRouter><SoftwareUpdatePage /></MemoryRouter>);
beforeAll(() => Object.defineProperty(window, 'crypto', { configurable: true, value: require('crypto').webcrypto }));
beforeEach(() => apiFetchJson.mockReset());

test('a clean install submits the reviewed commit once', async () => {
  apiFetchJson.mockResolvedValueOnce(release).mockResolvedValueOnce({
    id: 'test', stage: 'queued', release: release.release, started: Date.now() / 1000,
  });
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Update to v1.1.0' }));
  const [path, options] = apiFetchJson.mock.calls[1];
  expect(path).toBe(endpoints.installSoftwareUpdate);
  expect(JSON.parse(options.body)).toMatchObject({ commit: release.commit, review: release.review, save_edits: false });
  expect(await screen.findByText(/Starting update/)).toBeInTheDocument();
});

test('edits require review and cancellation sends no install request', async () => {
  apiFetchJson.mockResolvedValue({ ...release, changes: ['dashboard/local.js'] });
  mount();
  fireEvent.click(await screen.findByText('Update to v1.1.0'));
  expect(screen.getByText('dashboard/local.js')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(apiFetchJson).toHaveBeenCalledTimes(1);
});

test('offline and ahead installations keep their current revision', async () => {
  apiFetchJson.mockResolvedValue({ ...release, state: 'ahead', error: 'Offline · last known release' });
  mount();
  expect(await screen.findByText('Ahead of the latest stable release')).toBeInTheDocument();
  expect(screen.getByText(/Offline/)).toBeInTheDocument();
  expect(screen.queryByText('Update to v1.1.0')).not.toBeInTheDocument();
});

test('a declined installation retains the specific error after refresh', async () => {
  apiFetchJson.mockResolvedValueOnce(release).mockRejectedValueOnce(new Error('Local files changed')).mockResolvedValue(release);
  mount();
  fireEvent.click(await screen.findByText('Update to v1.1.0'));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Local files changed'));
});

test('reopening a completed job leads directly to Config Sync', async () => {
  apiFetchJson.mockResolvedValue({ ...release, state: 'current', job: { stage: 'updated', release: release.release, settings_pending: true } });
  mount();
  expect(await screen.findByRole('link', { name: 'Review settings changes' })).toHaveAttribute('href', '/settings?review=defaults');
});
