import axios from 'axios';

const DEFAULT_CSRF_HEADER_NAME = 'X-PixEagle-CSRF';
const AUTH_FAILURE_EVENT = 'pixeagle-api-auth-failure';
const SAFE_HTTP_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

let axiosAuthInstalled = false;

let authSessionState = {
  authMode: null,
  authenticated: false,
  principal: null,
  csrfRequired: false,
  csrfHeaderName: process.env.REACT_APP_CSRF_HEADER_NAME || DEFAULT_CSRF_HEADER_NAME,
  csrfToken: null,
  expiresAt: null,
};

const subscribers = new Set();

const getConfiguredCsrfHeaderName = () => (
  authSessionState?.csrfHeaderName
  || process.env.REACT_APP_CSRF_HEADER_NAME
  || DEFAULT_CSRF_HEADER_NAME
);

const normalizeMethod = (method) => String(method || 'GET').toUpperCase();

const mutationNeedsCsrf = (method) => (
  !SAFE_HTTP_METHODS.has(normalizeMethod(method))
);

const notifySubscribers = () => {
  subscribers.forEach((listener) => {
    try {
      listener(getDashboardAuthSession());
    } catch (error) {
      // Keep auth propagation best-effort; one listener should not break others.
      console.error('Dashboard auth listener failed:', error);
    }
  });
};

export const getDashboardAuthSession = () => ({ ...authSessionState });

export const subscribeDashboardAuthSession = (listener) => {
  subscribers.add(listener);
  return () => subscribers.delete(listener);
};

export const setDashboardAuthSession = (session) => {
  authSessionState = {
    authMode: session?.auth_mode || session?.authMode || null,
    authenticated: Boolean(session?.authenticated),
    principal: session?.principal || null,
    csrfRequired: Boolean(session?.csrf_required ?? session?.csrfRequired),
    csrfHeaderName: session?.csrf_header_name || session?.csrfHeaderName || getConfiguredCsrfHeaderName(),
    csrfToken: session?.csrf_token || session?.csrfToken || null,
    expiresAt: session?.expires_at || session?.expiresAt || null,
  };
  notifySubscribers();
};

export const clearDashboardAuthSession = (authMode = authSessionState.authMode) => {
  setDashboardAuthSession({
    auth_mode: authMode,
    authenticated: false,
    principal: null,
    csrf_required: authMode === 'browser_session',
    csrf_token: null,
    expires_at: null,
  });
};

export const isBrowserSessionAuthMode = () => (
  authSessionState.authMode === 'browser_session'
);

export const hasDashboardScope = (scope) => {
  if (!isBrowserSessionAuthMode()) {
    return true;
  }
  return Boolean(authSessionState.principal?.scopes?.includes(scope));
};

export const canOpenDashboardMedia = () => (
  !isBrowserSessionAuthMode()
  || (authSessionState.authenticated && hasDashboardScope('media:read'))
);

export const getMediaElementCrossOrigin = () => (
  isBrowserSessionAuthMode() ? 'use-credentials' : undefined
);

export const getMediaElementAuthProps = () => {
  const crossOrigin = getMediaElementCrossOrigin();
  return crossOrigin ? { crossOrigin } : {};
};

const dispatchAuthFailure = (status, url) => {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') {
    return;
  }
  window.dispatchEvent(new CustomEvent(AUTH_FAILURE_EVENT, {
    detail: { status, url },
  }));
};

const addCsrfHeader = (headers, method) => {
  if (!mutationNeedsCsrf(method) || !authSessionState.csrfToken) {
    return headers;
  }

  const headerName = getConfiguredCsrfHeaderName();
  if (headers instanceof Headers) {
    if (!headers.has(headerName)) {
      headers.set(headerName, authSessionState.csrfToken);
    }
    return headers;
  }

  const nextHeaders = { ...(headers || {}) };
  const existingHeader = Object.keys(nextHeaders).find(
    (name) => name.toLowerCase() === headerName.toLowerCase()
  );
  if (!existingHeader) {
    nextHeaders[headerName] = authSessionState.csrfToken;
  }
  return nextHeaders;
};

export const buildApiFetchOptions = (options = {}) => {
  const method = normalizeMethod(options.method);
  const headers = addCsrfHeader(new Headers(options.headers || {}), method);
  return {
    ...options,
    method,
    headers,
    credentials: options.credentials || 'include',
  };
};

export const apiFetch = async (input, options = {}) => {
  const response = await fetch(input, buildApiFetchOptions(options));
  if (response.status === 401 || response.status === 403) {
    dispatchAuthFailure(response.status, typeof input === 'string' ? input : input?.url);
  }
  return response;
};

export const apiFetchJson = async (input, options = {}) => {
  const response = await apiFetch(input, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  let data;
  if (response.ok) {
    data = await response.json();
  } else {
    try {
      data = await response.json();
    } catch {
      data = {};
    }
  }
  if (!response.ok) {
    const message = data?.detail?.message || data?.detail || data?.error || data?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.response = response;
    error.data = data;
    throw error;
  }
  return data;
};

export const apiFetchBlob = async (input, options = {}) => {
  const response = await apiFetch(input, options);
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      message = payload?.detail?.message || payload?.detail || payload?.error || payload?.message || message;
    } catch {
      try {
        message = await response.text();
      } catch {
        // Keep the status fallback.
      }
    }
    const error = new Error(message);
    error.response = response;
    throw error;
  }
  return response.blob();
};

export const downloadApiBlob = async (url, filename) => {
  const blob = await apiFetchBlob(url);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
};

export const createDashboardWebSocket = (url) => {
  if (!canOpenDashboardMedia()) {
    throw new Error('Authenticated media session with media:read scope is required.');
  }
  return new WebSocket(url);
};

export const isWebSocketAuthClose = (event) => event?.code === 1008;

export const installDashboardAxiosAuth = () => {
  if (axiosAuthInstalled) {
    return;
  }
  axiosAuthInstalled = true;

  if (axios.defaults) {
    axios.defaults.withCredentials = true;
  }

  if (axios.interceptors?.request?.use) {
    axios.interceptors.request.use((config) => {
      const nextConfig = { ...config, withCredentials: config.withCredentials !== false };
      const method = normalizeMethod(nextConfig.method);
      nextConfig.headers = addCsrfHeader(nextConfig.headers || {}, method);
      return nextConfig;
    });
  }

  if (axios.interceptors?.response?.use) {
    axios.interceptors.response.use(
      (response) => response,
      (error) => {
        const status = error?.response?.status;
        if (status === 401 || status === 403) {
          dispatchAuthFailure(status, error?.config?.url);
        }
        return Promise.reject(error);
      }
    );
  }
};

installDashboardAxiosAuth();

export const DASHBOARD_AUTH_FAILURE_EVENT = AUTH_FAILURE_EVENT;
export const DASHBOARD_CSRF_HEADER_NAME = DEFAULT_CSRF_HEADER_NAME;

export default axios;
