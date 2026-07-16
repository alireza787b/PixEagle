import { isSystemRestartTier } from './SettingsPage';

describe('Settings restart tier handling', () => {
  test('prompts only for the exact system_restart tier', () => {
    expect(isSystemRestartTier('system_restart')).toBe(true);
    expect(isSystemRestartTier('follower_restart')).toBe(false);
    expect(isSystemRestartTier('tracker_restart')).toBe(false);
    expect(isSystemRestartTier('immediate')).toBe(false);
    expect(isSystemRestartTier('SYSTEM_RESTART')).toBe(false);
    expect(isSystemRestartTier(undefined)).toBe(false);
  });
});
