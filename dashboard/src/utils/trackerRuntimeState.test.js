import { getTrackerRuntimeState, trackerHasRuntimeOutput } from './trackerRuntimeState';

describe('getTrackerRuntimeState', () => {
  test('distinguishes inactive visible output from active usable tracking', () => {
    const state = getTrackerRuntimeState({
      active: false,
      has_output: true,
      usable_for_following: false,
      fields: {
        angular: { value: [12, -4, 0], type: 'angular_3d' }
      }
    });

    expect(state.state).toBe('visible_output');
    expect(state.label).toBe('Output Visible');
    expect(state.followLabel).toBe('Not For Follow');
    expect(state.hasOutput).toBe(true);
    expect(state.activeTracking).toBe(false);
    expect(state.usableForFollowing).toBe(false);
    expect(trackerHasRuntimeOutput({ has_output: true })).toBe(true);
  });

  test('honors stale output as unusable even when tracking is active', () => {
    const state = getTrackerRuntimeState({
      active: true,
      has_output: true,
      raw_data: {
        data_is_stale: true,
        usable_for_following: false
      }
    });

    expect(state.state).toBe('stale_output');
    expect(state.label).toBe('Stale Output');
    expect(state.usableForFollowing).toBe(false);
    expect(state.dataIsStale).toBe(true);
  });

  test('marks active fresh output as follower usable when explicit flags allow it', () => {
    const state = getTrackerRuntimeState({
      active: true,
      has_output: true,
      usable_for_following: true
    });

    expect(state.state).toBe('active_usable');
    expect(state.label).toBe('Active');
    expect(state.followLabel).toBe('Follower Usable');
    expect(state.usableForFollowing).toBe(true);
  });
});
