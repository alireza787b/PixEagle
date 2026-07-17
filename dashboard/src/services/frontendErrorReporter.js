import { endpoints } from './apiEndpoints';
import { apiFetchJson, getDashboardAuthSession, hasDashboardScope } from './apiClient';

const MAX_REPORTS_PER_MINUTE = 20;
const REPORT_SCOPE = 'runtime:report';
const SECRET_PATTERNS = [
  [
    /\b(authorization|proxy-authorization|cookie|set-cookie|x-pixeagle-csrf)(\s*[:=]\s*)([^,\r\n]+)/gi,
    '$1$2[REDACTED]',
  ],
  [
    /\b(password|passwd|token|secret|api[_-]?key|csrf|session[_-]?id)(\s*[:=]\s*)([^,\s"'}]{3,})/gi,
    '$1$2[REDACTED]',
  ],
  [/([a-z][a-z0-9+.-]*:\/\/)([^/@\s]+)@/gi, '$1[REDACTED]@'],
];

let installed = false;
let recentReports = [];

const stripUrlSecrets = (value) => {
  if (!value) {
    return undefined;
  }
  try {
    const parsed = new URL(String(value), window.location.origin);
    return `${parsed.origin}${parsed.pathname}`;
  } catch {
    return String(value).split(/[?#]/, 1)[0];
  }
};

const stripRouteSecrets = (value) => {
  if (!value) {
    return undefined;
  }
  return String(value).split(/[?#]/, 1)[0];
};

const clampText = (value, maxLength) => {
  if (value === undefined || value === null) {
    return undefined;
  }
  let text = String(value);
  SECRET_PATTERNS.forEach(([pattern, replacement]) => {
    text = text.replace(pattern, replacement);
  });
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
};

const currentRoute = () => {
  if (typeof window === 'undefined') {
    return undefined;
  }
  return window.location.pathname;
};

const canReportFrontendError = () => {
  const session = getDashboardAuthSession();
  if (!session.authMode) {
    return false;
  }
  if (session.authMode !== 'browser_session') {
    return true;
  }
  return Boolean(session.authenticated && hasDashboardScope(REPORT_SCOPE));
};

const underClientRateLimit = (now = Date.now()) => {
  const cutoff = now - 60_000;
  recentReports = recentReports.filter((timestamp) => timestamp >= cutoff);
  if (recentReports.length >= MAX_REPORTS_PER_MINUTE) {
    return false;
  }
  recentReports.push(now);
  return true;
};

const normalizeErrorReport = (input, overrides = {}) => {
  const error = input instanceof Error ? input : null;
  const message = error?.message || input?.message || input || 'Dashboard runtime error';
  return {
    source: 'dashboard',
    level: 'ERROR',
    name: clampText(error?.name || input?.name || overrides.name, 160),
    message: clampText(message, 2000) || 'Dashboard runtime error',
    stack: clampText(error?.stack || input?.stack || overrides.stack, 8000),
    url: clampText(
      stripUrlSecrets(overrides.url || (typeof window !== 'undefined' ? window.location.href : undefined)),
      2048
    ),
    route: clampText(stripRouteSecrets(overrides.route || currentRoute()), 512),
    user_agent: clampText(
      overrides.userAgent || (typeof navigator !== 'undefined' ? navigator.userAgent : undefined),
      512
    ),
    context: {
      kind: clampText(overrides.kind || input?.kind || 'runtime_error', 80),
      component_stack: clampText(overrides.componentStack, 2000),
    },
  };
};

export const reportFrontendError = async (input, overrides = {}) => {
  if (!canReportFrontendError() || !underClientRateLimit()) {
    return { skipped: true };
  }
  const payload = normalizeErrorReport(input, overrides);
  try {
    return await apiFetchJson(endpoints.frontendErrorReport, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  } catch {
    return { skipped: true };
  }
};

export const installFrontendErrorReporter = () => {
  if (installed || typeof window === 'undefined') {
    return () => {};
  }
  installed = true;

  const onError = (event) => {
    reportFrontendError(event.error || event.message || 'Window error', {
      kind: 'window_error',
      url: event.filename || window.location.href,
    });
  };
  const onUnhandledRejection = (event) => {
    const reason = event.reason;
    reportFrontendError(
      reason instanceof Error ? reason : { message: String(reason || 'Unhandled promise rejection') },
      { kind: 'unhandled_rejection' }
    );
  };

  window.addEventListener('error', onError);
  window.addEventListener('unhandledrejection', onUnhandledRejection);

  return () => {
    window.removeEventListener('error', onError);
    window.removeEventListener('unhandledrejection', onUnhandledRejection);
    installed = false;
  };
};

export const resetFrontendErrorReporterForTests = () => {
  installed = false;
  recentReports = [];
};
