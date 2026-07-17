import { apiFetchJson } from './apiClient';
import { endpoints } from './apiEndpoints';
import {
  changeOwnPassword,
  createBrowserUser,
  deleteBrowserUser,
  listBrowserUsers,
  sessionPayloadFromPasswordChange,
  updateBrowserUser,
} from './browserAccountApi';

jest.mock('./apiClient', () => ({
  apiFetchJson: jest.fn(),
}));

beforeEach(() => {
  apiFetchJson.mockReset();
});

test('normalizes user inventory without exposing credential fields', async () => {
  apiFetchJson.mockResolvedValue({
    users: [{
      username: 'admin',
      role: 'admin',
      enabled: true,
      password_pbkdf2_sha256: 'must-not-reach-the-ui',
      password: 'also-hidden',
    }],
  });

  await expect(listBrowserUsers()).resolves.toEqual([
    { username: 'admin', role: 'admin', enabled: true },
  ]);
  expect(apiFetchJson).toHaveBeenCalledWith(endpoints.authUsers);
});

test('uses typed account mutation endpoints and request bodies', async () => {
  apiFetchJson.mockResolvedValue({ status: 'success' });

  await createBrowserUser({
    username: 'flight operator',
    role: 'operator',
    password: 'initial-secret',
    enabled: true,
  });
  await updateBrowserUser('flight operator', { role: 'viewer' });
  await deleteBrowserUser('flight operator');
  await changeOwnPassword({ currentPassword: 'old-secret', newPassword: 'new-secret' });

  expect(apiFetchJson).toHaveBeenNthCalledWith(1, endpoints.authUsers, {
    method: 'POST',
    body: JSON.stringify({
      username: 'flight operator',
      role: 'operator',
      password: 'initial-secret',
      enabled: true,
    }),
  });
  expect(apiFetchJson).toHaveBeenNthCalledWith(2, endpoints.authUser('flight operator'), {
    method: 'PATCH',
    body: JSON.stringify({ role: 'viewer' }),
  });
  expect(apiFetchJson).toHaveBeenNthCalledWith(3, endpoints.authUser('flight operator'), {
    method: 'DELETE',
    body: JSON.stringify({ confirm_username: 'flight operator' }),
  });
  expect(apiFetchJson).toHaveBeenNthCalledWith(4, endpoints.authPassword, {
    method: 'POST',
    body: JSON.stringify({
      current_password: 'old-secret',
      new_password: 'new-secret',
    }),
  });
});

test('rejects malformed user inventory instead of rendering ambiguous metadata', async () => {
  apiFetchJson.mockResolvedValue({ users: [{ username: 'broken', role: 'unknown' }] });

  await expect(listBrowserUsers()).rejects.toThrow(/invalid account metadata/i);
});

test('extracts only complete replacement-session payloads', () => {
  const replacement = {
    authenticated: true,
    auth_mode: 'browser_session',
    csrf_required: true,
    csrf_header_name: 'X-PixEagle-CSRF',
    csrf_token: 'replacement-csrf',
    expires_at: 1784275200,
    principal: { subject: 'operator', role: 'operator', scopes: [] },
  };

  expect(sessionPayloadFromPasswordChange(replacement)).toBe(replacement);
  expect(sessionPayloadFromPasswordChange({ session: replacement })).toBe(replacement);
  expect(sessionPayloadFromPasswordChange({ user: { username: 'operator' } })).toBeNull();
  expect(sessionPayloadFromPasswordChange({
    ...replacement,
    csrf_token: null,
  })).toBeNull();
  expect(sessionPayloadFromPasswordChange({
    ...replacement,
    principal: { ...replacement.principal, role: 'unknown' },
  })).toBeNull();
});
