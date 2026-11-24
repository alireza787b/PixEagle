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

const followingStartFailureMessages = new Map([
  ['image_measurement_unavailable', 'Target measurement is not current. Reacquire the target before starting.'],
  ['image_receipt_stale', 'Target measurement is not current. Reacquire the target before starting.'],
  ['source_attitude_alignment_unavailable', 'Camera and aircraft timing are not aligned. Wait for current tracking before starting.'],
  ['target_not_tracking', 'Target is not being tracked. Select or reacquire a target before starting.'],
  ['following_input_context_changed', 'Target or camera changed. Reacquire the target before starting.'],
  ['guidance_image_geometry_changed', 'Camera geometry changed. Reacquire the target before starting.'],
]);

export const followingStartFailureMessage = (data) => {
  const code = data?.result?.legacy_result?.details?.precondition?.code
    ?? data?.result?.outcome?.precondition?.code ?? data?.code;
  return followingStartFailureMessages.get(code) || 'Following did not start. Check aircraft and tracking status.';
};
