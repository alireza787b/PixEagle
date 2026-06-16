const generateActionIdempotencyKey = (reason) => {
  const randomSuffix = Math.random().toString(36).slice(2, 10);
  return `dashboard-${reason.replace(/_/g, '-')}-${Date.now()}-${randomSuffix}`;
};

export const buildActionRequest = (
  reason,
  metadata = { ui: 'dashboard_control_panel' }
) => ({
  source: 'dashboard',
  reason,
  confirm: true,
  idempotency_key: generateActionIdempotencyKey(reason),
  metadata,
});
