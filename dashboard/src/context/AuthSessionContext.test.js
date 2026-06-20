import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  AuthSessionProvider,
  useAuthSession,
} from './AuthSessionContext';
import {
  DASHBOARD_AUTH_FAILURE_EVENT,
  clearDashboardAuthSession,
} from '../services/apiClient';

const responseJson = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
});

const authenticatedOperatorSession = {
  auth_mode: 'browser_session',
  authenticated: true,
  principal: {
    subject: 'operator',
    role: 'operator',
    scopes: ['media:read', 'actions:execute'],
  },
  csrf_required: true,
  csrf_header_name: 'X-PixEagle-CSRF',
  csrf_token: 'csrf-token',
  expires_at: '2026-06-19T18:00:00Z',
};

const anonymousBrowserSession = {
  auth_mode: 'browser_session',
  authenticated: false,
  principal: null,
  csrf_required: true,
  csrf_header_name: 'X-PixEagle-CSRF',
  csrf_token: null,
  expires_at: null,
};

function AuthProbe() {
  const auth = useAuthSession();
  return (
    <div>
      <span data-testid="loading">{String(auth.loading)}</span>
      <span data-testid="authenticated">{String(auth.authenticated)}</span>
      <span data-testid="requires-login">{String(auth.requiresLogin)}</span>
      <span data-testid="subject">{auth.principal?.subject || 'none'}</span>
      <button type="button" onClick={() => auth.logout()}>
        logout
      </button>
    </div>
  );
}

describe('AuthSessionProvider adversarial browser-session handling', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = jest.fn();
    clearDashboardAuthSession(null);
  });

  afterEach(() => {
    jest.restoreAllMocks();
    global.fetch = originalFetch;
  });

  test('refreshes to login-required state after protected media auth failure', async () => {
    global.fetch
      .mockResolvedValueOnce(responseJson(authenticatedOperatorSession))
      .mockResolvedValueOnce(responseJson(anonymousBrowserSession));

    render(
      <AuthSessionProvider>
        <AuthProbe />
      </AuthSessionProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent(DASHBOARD_AUTH_FAILURE_EVENT, {
        detail: { status: 401, url: '/api/v1/streams/media-health' },
      }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    });
    expect(screen.getByTestId('requires-login')).toHaveTextContent('true');
    expect(screen.getByTestId('subject')).toHaveTextContent('none');

    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  test('clears browser session when silent refresh after auth failure fails', async () => {
    global.fetch
      .mockResolvedValueOnce(responseJson(authenticatedOperatorSession))
      .mockRejectedValueOnce(new Error('session endpoint unavailable'));

    render(
      <AuthSessionProvider>
        <AuthProbe />
      </AuthSessionProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent(DASHBOARD_AUTH_FAILURE_EVENT, {
        detail: { status: 403, url: '/api/v1/actions/tracking-start' },
      }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    });
    expect(screen.getByTestId('requires-login')).toHaveTextContent('true');
  });

  test('logout sends CSRF and clears local session even when backend says cookie expired', async () => {
    global.fetch
      .mockResolvedValueOnce(responseJson(authenticatedOperatorSession))
      .mockResolvedValueOnce(responseJson({ code: 'invalid_session' }, 401));

    render(
      <AuthSessionProvider>
        <AuthProbe />
      </AuthSessionProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
    });

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    });
    expect(screen.getByTestId('requires-login')).toHaveTextContent('true');

    const logoutOptions = global.fetch.mock.calls[1][1];
    expect(logoutOptions.method).toBe('POST');
    expect(logoutOptions.credentials).toBe('include');
    expect(logoutOptions.headers.get('X-PixEagle-CSRF')).toBe('csrf-token');
  });
});
