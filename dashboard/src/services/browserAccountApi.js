import { apiFetchJson } from './apiClient';
import { endpoints } from './apiEndpoints';

export const BROWSER_USER_ROLES = Object.freeze(['viewer', 'operator', 'admin']);

const normalizeBrowserUser = (record) => {
  if (!record || typeof record !== 'object' || typeof record.username !== 'string') {
    throw new Error('PixEagle returned an invalid browser-user record.');
  }
  if (!BROWSER_USER_ROLES.includes(record.role) || typeof record.enabled !== 'boolean') {
    throw new Error(`PixEagle returned invalid account metadata for ${record.username}.`);
  }

  // Deliberately whitelist public metadata so credential material cannot reach the UI.
  return {
    username: record.username,
    role: record.role,
    enabled: record.enabled,
  };
};

export const listBrowserUsers = async () => {
  const payload = await apiFetchJson(endpoints.authUsers);
  const records = Array.isArray(payload) ? payload : payload?.users;
  if (!Array.isArray(records)) {
    throw new Error('PixEagle returned an invalid browser-user list.');
  }
  return records.map(normalizeBrowserUser);
};

export const createBrowserUser = ({ username, role, password, enabled }) => (
  apiFetchJson(endpoints.authUsers, {
    method: 'POST',
    body: JSON.stringify({ username, role, password, enabled }),
  })
);

export const updateBrowserUser = (username, changes) => (
  apiFetchJson(endpoints.authUser(username), {
    method: 'PATCH',
    body: JSON.stringify(changes),
  })
);

export const deleteBrowserUser = (username) => (
  apiFetchJson(endpoints.authUser(username), {
    method: 'DELETE',
    body: JSON.stringify({ confirm_username: username }),
  })
);

const TOKEN_STATES = Object.freeze(['active', 'expired', 'revoked', 'inactive']);

const normalizeAuthToken = (record) => {
  if (
    !record
    || typeof record !== 'object'
    || typeof record.token_id !== 'string'
    || typeof record.name !== 'string'
    || typeof record.subject !== 'string'
    || !TOKEN_STATES.includes(record.state)
    || !Array.isArray(record.scopes)
  ) {
    throw new Error('PixEagle returned an invalid API-token record.');
  }
  return {
    token_id: record.token_id,
    name: record.name,
    subject: record.subject,
    scopes: record.scopes.filter((scope) => typeof scope === 'string'),
    state: record.state,
    created_at: record.created_at || null,
    expires_at: record.expires_at || null,
    revoked_at: record.revoked_at || null,
    last_used_at: record.last_used_at || null,
  };
};

export const listBearerTokens = async () => {
  const payload = await apiFetchJson(endpoints.authTokens);
  const records = Array.isArray(payload) ? payload : payload?.tokens;
  if (!Array.isArray(records)) {
    throw new Error('PixEagle returned an invalid API-token list.');
  }
  return records.map(normalizeAuthToken);
};

export const createBearerToken = ({ name, scopes = ['media:read'], expiresInDays = 90 }) => (
  apiFetchJson(endpoints.authTokens, {
    method: 'POST',
    body: JSON.stringify({
      name,
      scopes,
      expires_in_days: expiresInDays,
    }),
  })
);

export const revokeBearerToken = (tokenId) => (
  apiFetchJson(endpoints.authToken(tokenId), {
    method: 'DELETE',
  })
);

export const changeOwnPassword = ({ currentPassword, newPassword }) => (
  apiFetchJson(endpoints.authPassword, {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
);

export const sessionPayloadFromPasswordChange = (payload) => {
  const candidate = payload?.session || payload?.replacement_session || payload;
  if (
    !candidate
    || typeof candidate !== 'object'
    || candidate.authenticated !== true
    || candidate.auth_mode !== 'browser_session'
    || candidate.csrf_required !== true
    || typeof candidate.csrf_header_name !== 'string'
    || !candidate.csrf_header_name
    || typeof candidate.csrf_token !== 'string'
    || !candidate.csrf_token
    || typeof candidate.expires_at !== 'number'
    || !Number.isFinite(candidate.expires_at)
    || !candidate.principal
    || typeof candidate.principal !== 'object'
    || typeof candidate.principal.subject !== 'string'
    || !candidate.principal.subject
    || !BROWSER_USER_ROLES.includes(candidate.principal.role)
    || !Array.isArray(candidate.principal.scopes)
    || candidate.principal.scopes.some((scope) => typeof scope !== 'string')
  ) {
    return null;
  }
  return candidate;
};
