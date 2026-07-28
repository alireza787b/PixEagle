import { restartAvailabilityMessage } from './PendingRestartBanner';

test('explains the old backend response after an in-place source update', () => {
  expect(restartAvailabilityMessage('no_pending_system_restart_changes')).toBe(
    'This backend predates manual restart support. Restart PixEagle once from the host to finish the update.'
  );
});

test('keeps flight-state restart rejection explicit', () => {
  expect(restartAvailabilityMessage('following_or_offboard_active')).toBe(
    'Stop following and leave Offboard before restarting.'
  );
});

test('uses a bounded fallback for unknown availability states', () => {
  expect(restartAvailabilityMessage('future_reason')).toBe(
    'System restart is unavailable for this runtime.'
  );
});
