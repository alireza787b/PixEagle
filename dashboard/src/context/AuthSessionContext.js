import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { endpoints } from '../services/apiEndpoints';
import {
  DASHBOARD_AUTH_FAILURE_EVENT,
  apiFetch,
  apiFetchJson,
  clearDashboardAuthSession,
  setDashboardAuthSession,
  subscribeDashboardAuthSession,
} from '../services/apiClient';

const AuthSessionContext = createContext(null);

const initialSessionState = {
  authMode: null,
  authenticated: false,
  principal: null,
  csrfRequired: false,
  csrfHeaderName: null,
  csrfToken: null,
  expiresAt: null,
};

const normalizeSession = (session) => ({
  authMode: session?.auth_mode || session?.authMode || null,
  authenticated: Boolean(session?.authenticated),
  principal: session?.principal || null,
  csrfRequired: Boolean(session?.csrf_required ?? session?.csrfRequired),
  csrfHeaderName: session?.csrf_header_name || session?.csrfHeaderName || null,
  csrfToken: session?.csrf_token || session?.csrfToken || null,
  expiresAt: session?.expires_at || session?.expiresAt || null,
});

const parseErrorBody = async (response) => {
  try {
    return await response.json();
  } catch {
    return {};
  }
};

const errorMessageFromPayload = (payload, fallback) => (
  payload?.detail?.message
  || payload?.detail
  || payload?.error
  || payload?.message
  || payload?.code
  || fallback
);

export const AuthSessionProvider = ({ children }) => {
  const [session, setSession] = useState(initialSessionState);
  const [loading, setLoading] = useState(true);
  const [loginPending, setLoginPending] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const [error, setError] = useState(null);
  const authOperationGenerationRef = useRef(0);

  useEffect(() => (
    subscribeDashboardAuthSession((nextSession) => {
      setSession(normalizeSession(nextSession));
    })
  ), []);

  const applySession = useCallback((payload, expectedGeneration = null) => {
    if (
      expectedGeneration !== null
      && expectedGeneration !== authOperationGenerationRef.current
    ) {
      return null;
    }
    setDashboardAuthSession(payload);
    setSession(normalizeSession(payload));
    setError(null);
    return normalizeSession(payload);
  }, []);

  const refreshSession = useCallback(async ({ silent = false } = {}) => {
    const operationGeneration = authOperationGenerationRef.current;
    if (!silent) {
      setLoading(true);
    }
    try {
      const response = await apiFetch(endpoints.authSession, {
        method: 'GET',
        headers: {
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
        },
      });
      const payload = await parseErrorBody(response);
      if (!response.ok) {
        throw new Error(errorMessageFromPayload(payload, `HTTP ${response.status}`));
      }
      return applySession(payload, operationGeneration);
    } catch (refreshError) {
      if (!silent) {
        setError(refreshError.message || 'Unable to reach PixEagle auth session.');
      }
      throw refreshError;
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [applySession]);

  const login = useCallback(async ({ username, password }) => {
    authOperationGenerationRef.current += 1;
    const operationGeneration = authOperationGenerationRef.current;
    setLoginPending(true);
    setError(null);
    try {
      const payload = await apiFetchJson(endpoints.authLogin, {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      return applySession(payload, operationGeneration);
    } catch (loginError) {
      const message = loginError?.data
        ? errorMessageFromPayload(loginError.data, 'Login failed.')
        : loginError.message || 'Login failed.';
      setError(message);
      throw new Error(message);
    } finally {
      setLoginPending(false);
    }
  }, [applySession]);

  const logout = useCallback(async () => {
    authOperationGenerationRef.current += 1;
    setLogoutPending(true);
    setError(null);
    try {
      await apiFetch(endpoints.authLogout, { method: 'POST' });
    } catch (logoutError) {
      if (logoutError?.response?.status !== 401) {
        setError(logoutError.message || 'Logout failed.');
      }
    } finally {
      clearDashboardAuthSession(session.authMode);
      setLogoutPending(false);
    }
  }, [session.authMode]);

  useEffect(() => {
    refreshSession().catch(() => {});
  }, [refreshSession]);

  useEffect(() => {
    const handleAuthFailure = () => {
      if (session.authMode === 'browser_session') {
        authOperationGenerationRef.current += 1;
        refreshSession({ silent: true }).catch(() => {
          clearDashboardAuthSession('browser_session');
        });
      }
    };
    window.addEventListener(DASHBOARD_AUTH_FAILURE_EVENT, handleAuthFailure);
    return () => window.removeEventListener(DASHBOARD_AUTH_FAILURE_EVENT, handleAuthFailure);
  }, [refreshSession, session.authMode]);

  const value = useMemo(() => ({
    ...session,
    loading,
    loginPending,
    logoutPending,
    error,
    requiresLogin: session.authMode === 'browser_session' && !session.authenticated,
    usesBrowserSession: session.authMode === 'browser_session',
    hasScope: (scope) => {
      if (session.authMode !== 'browser_session') {
        return true;
      }
      return Boolean(session.principal?.scopes?.includes(scope));
    },
    hasAnyScope: (scopes) => {
      if (session.authMode !== 'browser_session') {
        return true;
      }
      return scopes.some((scope) => session.principal?.scopes?.includes(scope));
    },
    refreshSession,
    captureAuthOperationGeneration: () => authOperationGenerationRef.current,
    authOperationIsCurrent: (generation) => (
      generation === authOperationGenerationRef.current
    ),
    replaceSession: applySession,
    replaceSessionIfCurrent: (payload, generation) => (
      applySession(payload, generation)
    ),
    login,
    logout,
    clearError: () => setError(null),
  }), [
    session,
    loading,
    loginPending,
    logoutPending,
    error,
    applySession,
    refreshSession,
    login,
    logout,
  ]);

  return (
    <AuthSessionContext.Provider value={value}>
      {children}
    </AuthSessionContext.Provider>
  );
};

export const useAuthSession = () => {
  const value = useContext(AuthSessionContext);
  if (!value) {
    throw new Error('useAuthSession must be used inside AuthSessionProvider');
  }
  return value;
};
