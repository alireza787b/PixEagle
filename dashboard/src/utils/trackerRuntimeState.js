const firstDefined = (...values) => values.find((value) => value !== undefined && value !== null);

const parseBooleanLike = (value) => {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', 'yes', '1', 'active', 'tracking', 'tracking_active', 'receiving'].includes(normalized)) {
      return true;
    }
    if (['false', 'no', '0', 'inactive', 'disabled', 'lost', 'stale', 'none'].includes(normalized)) {
      return false;
    }
  }
  return Boolean(value);
};

const hasFieldOutput = (fields = {}) => (
  Object.values(fields).some((fieldData) => {
    if (!fieldData || typeof fieldData !== 'object') {
      return fieldData !== undefined && fieldData !== null;
    }
    return fieldData.value !== undefined && fieldData.value !== null;
  })
);

export const getTrackerRuntimeState = (currentStatus) => {
  const rawData = currentStatus?.raw_data || {};
  const metadata = currentStatus?.metadata || rawData.metadata || {};
  const fields = currentStatus?.fields || {};

  const activeValue = firstDefined(
    currentStatus?.active,
    currentStatus?.tracking_active,
    rawData.tracking_active,
    rawData.gimbal_tracking_active
  );
  const activeTracking = parseBooleanLike(activeValue);

  const explicitHasOutput = firstDefined(
    currentStatus?.has_output,
    rawData.has_output,
    metadata.has_output
  );
  const hasOutput = explicitHasOutput !== undefined
    ? parseBooleanLike(explicitHasOutput)
    : Boolean(activeTracking || hasFieldOutput(fields));

  const dataIsStale = parseBooleanLike(firstDefined(
    currentStatus?.data_is_stale,
    rawData.data_is_stale,
    metadata.data_is_stale,
    rawData.stale,
    rawData.is_stale,
    false
  ));

  const explicitUsable = firstDefined(
    currentStatus?.usable_for_following,
    rawData.usable_for_following,
    metadata.usable_for_following
  );
  const usableForFollowing = explicitUsable !== undefined
    ? parseBooleanLike(explicitUsable)
    : Boolean(activeTracking && hasOutput && !dataIsStale);

  let state = 'no_output';
  let label = 'No Output';
  let color = 'default';
  let severity = 'info';
  let message = 'No tracker output is available.';

  if (hasOutput && dataIsStale) {
    state = 'stale_output';
    label = 'Stale Output';
    color = 'warning';
    severity = 'warning';
    message = 'Tracker output is stale and is not usable for follower control.';
  } else if (hasOutput && !usableForFollowing && !activeTracking) {
    state = 'visible_output';
    label = 'Output Visible';
    color = 'info';
    severity = 'warning';
    message = 'Tracker output is visible, but active target tracking is not confirmed.';
  } else if (hasOutput && !usableForFollowing) {
    state = 'not_usable';
    label = 'Not Usable';
    color = 'warning';
    severity = 'warning';
    message = 'Tracker output is not usable for follower control.';
  } else if (hasOutput && !activeTracking) {
    state = 'visible_output';
    label = 'Output Visible';
    color = 'info';
    severity = 'info';
    message = 'Tracker output is visible without active target tracking confirmation.';
  } else if (hasOutput && activeTracking) {
    state = 'active_usable';
    label = 'Active';
    color = 'success';
    severity = 'success';
    message = 'Tracker output is active and marked usable for follower control.';
  }

  return {
    state,
    label,
    color,
    severity,
    message,
    hasOutput,
    activeTracking,
    dataIsStale,
    usableForFollowing,
    followLabel: usableForFollowing ? 'Follower Usable' : 'Not For Follow',
    followColor: usableForFollowing ? 'success' : (hasOutput ? 'warning' : 'default'),
    rawData
  };
};

export const trackerHasRuntimeOutput = (currentStatus) => (
  getTrackerRuntimeState(currentStatus).hasOutput
);
