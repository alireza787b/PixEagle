import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';
import {
  normalizeTrackerCatalogForLegacyConsumers,
  useAvailableTrackers,
  useCurrentTracker,
  useSwitchTracker,
  useTrackerSelection,
} from './useTrackerSchema';

jest.mock('axios');

const typedCatalog = {
  schema_version: 1,
  source: 'tracking_catalog',
  status: 'available',
  consumer_guidance: 'selectable',
  configured_tracker: 'Gimbal',
  active_tracker: 'GimbalTracker',
  smart_mode_active: false,
  tracking_started: true,
  tracking_active: false,
  ui_trackers: [
    {
      name: 'Gimbal',
      display_name: 'External Gimbal',
      description: 'External gimbal packets.',
      short_description: 'External gimbal',
      data_type: 'GIMBAL_ANGLES',
      source: 'schema_manager',
      supported_schemas: ['GIMBAL_ANGLES'],
      capabilities: ['external_input'],
      suitable_for: ['seeker payload'],
      icon: 'T',
      performance_category: 'external',
    },
    {
      name: 'CSRT',
      display_name: 'CSRT',
      data_type: 'POSITION_2D',
      source: 'schema_manager',
      capabilities: ['manual_bbox'],
    },
  ],
  tracker_types: {
    SmartTracker: {
      name: 'SmartTracker',
      display_name: 'Smart Tracker',
      source: 'builtin_compatibility',
      data_type: 'BBOX_CONFIDENCE',
      smart_mode: true,
      available: true,
    },
  },
  total_trackers: 2,
  runtime_status: {
    source: 'tracker_runtime',
    status: 'visible_output',
    consumer_guidance: 'diagnostic_only',
    has_output: true,
    active_tracking: false,
    usable_for_following: true,
    data_is_stale: false,
    following_active: true,
    data_type: 'GIMBAL_ANGLES',
    timestamp: 1717200000,
  },
  health_issues: [],
  claim_boundary: 'process-local tracker catalog only',
  timestamp: 1717200000,
};

const typedCatalogResponse = () => Promise.resolve({ data: typedCatalog });

const SelectionProbe = () => {
  const { currentConfig, loading, error } = useTrackerSelection();
  if (loading) return <div>loading</div>;
  if (error) return <div>Error: {error}</div>;
  return <div>{currentConfig?.configured_tracker || 'none'}</div>;
};

const SelectionChangeProbe = () => {
  const { changeTrackerType, currentConfig, loading, error } = useTrackerSelection();
  const [result, setResult] = React.useState('idle');
  if (loading) return <div>loading</div>;
  if (error) return <div>Error: {error}</div>;
  return (
    <>
      <div>{currentConfig?.configured_tracker || 'none'}</div>
      <button onClick={async () => {
        const response = await changeTrackerType('Gimbal');
        setResult(response.status);
      }}>
        switch
      </button>
      <div>result:{result}</div>
    </>
  );
};

const AvailableTrackersProbe = () => {
  const { trackers, loading, error } = useAvailableTrackers(60000);
  if (loading) return <div>loading</div>;
  if (error) return <div>Error: {error}</div>;
  return <div>{Object.keys(trackers?.available_trackers || {}).join(',')}</div>;
};

const CurrentTrackerProbe = () => {
  const { currentTracker, loading, error } = useCurrentTracker(60000);
  if (loading) return <div>loading</div>;
  if (error) return <div>Error: {error}</div>;
  return <div>{currentTracker?.display_name || 'none'}</div>;
};

const SwitchTrackerProbe = () => {
  const { switchTracker, switching, switchError } = useSwitchTracker();
  const [result, setResult] = React.useState('idle');
  return (
    <>
      <button disabled={switching} onClick={async () => {
        const ok = await switchTracker('Gimbal');
        setResult(String(ok));
      }}>
        switch
      </button>
      <div>result:{result}</div>
      <div>{switchError || 'no-error'}</div>
    </>
  );
};

afterEach(() => {
  jest.restoreAllMocks();
  jest.clearAllMocks();
});

test('normalizes typed tracker catalog into legacy-compatible dashboard shapes', () => {
  const normalized = normalizeTrackerCatalogForLegacyConsumers(typedCatalog);

  expect(normalized.availableTrackers.available_trackers.Gimbal).toEqual(
    expect.objectContaining({
      display_name: 'External Gimbal',
      data_type: 'GIMBAL_ANGLES',
      ui_metadata: expect.objectContaining({
        display_name: 'External Gimbal',
        icon: 'T',
      }),
    })
  );
  expect(normalized.availableTrackers.current_configured).toBe('Gimbal');
  expect(normalized.currentConfig).toEqual(
    expect.objectContaining({
      configured_tracker: 'Gimbal',
      expected_data_type: 'GIMBAL_ANGLES',
      tracking_started: true,
      tracking_active: false,
    })
  );
  expect(normalized.currentTracker).toEqual(
    expect.objectContaining({
      tracker_type: 'Gimbal',
      active_tracker: 'GimbalTracker',
      display_name: 'External Gimbal',
      following_active: true,
      source: 'api_v1_tracking_catalog',
    })
  );
});

test('useTrackerSelection prefers typed tracker catalog over legacy config reads', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerCatalog) return typedCatalogResponse();
    return Promise.reject(new Error(`unexpected legacy read: ${url}`));
  });

  render(<SelectionProbe />);

  expect(await screen.findByText('Gimbal')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerCatalog);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerAvailableTypes);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerCurrentConfig);
});

test('useTrackerSelection changes tracker through typed action instead of deprecated set-type', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerCatalog) return typedCatalogResponse();
    return Promise.reject(new Error(`unexpected legacy read: ${url}`));
  });
  axios.post.mockResolvedValue({
    data: {
      status: 'success',
      result: {
        legacy_result: {
          action: 'tracker_switched',
          old_tracker: 'CSRT',
          new_tracker: 'Gimbal',
        },
      },
    },
  });

  render(<SelectionChangeProbe />);

  expect(await screen.findByText('Gimbal')).toBeInTheDocument();
  fireEvent.click(screen.getByText('switch'));

  await waitFor(() => {
    expect(screen.getByText('result:success')).toBeInTheDocument();
  });

  expect(axios.post).toHaveBeenCalledWith(
    endpoints.trackerSwitchAction,
    expect.objectContaining({
      source: 'dashboard',
      reason: 'switch_tracker',
      confirm: true,
      tracker_type: 'Gimbal',
      idempotency_key: expect.any(String),
      metadata: { ui: 'dashboard_tracker_selection' },
    })
  );
  expect(axios.post).not.toHaveBeenCalledWith(
    endpoints.trackerSetType,
    expect.anything()
  );
});

test('useAvailableTrackers and useCurrentTracker read typed tracker catalog', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerCatalog) return typedCatalogResponse();
    return Promise.reject(new Error(`unexpected legacy read: ${url}`));
  });

  render(
    <>
      <AvailableTrackersProbe />
      <CurrentTrackerProbe />
    </>
  );

  expect(await screen.findByText('Gimbal,CSRT')).toBeInTheDocument();
  expect(await screen.findByText('External Gimbal')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerCatalog);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerAvailable);
  expect(axios.get).not.toHaveBeenCalledWith(
    endpoints.trackerCurrent,
    expect.anything()
  );
});

test('useTrackerSelection falls back to legacy reads when typed catalog is absent', async () => {
  const consoleWarn = jest.spyOn(console, 'warn').mockImplementation(() => {});
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerCatalog) {
      return Promise.reject({ response: { status: 404 }, message: 'not found' });
    }
    if (url === endpoints.trackerAvailableTypes) {
      return Promise.resolve({
        data: {
          available_trackers: {
            CSRT: { display_name: 'CSRT', data_type: 'POSITION_2D' },
          },
        },
      });
    }
    if (url === endpoints.trackerCurrentConfig) {
      return Promise.resolve({
        data: {
          configured_tracker: 'CSRT',
          expected_data_type: 'POSITION_2D',
        },
      });
    }
    return Promise.reject(new Error(`unexpected endpoint: ${url}`));
  });

  render(<SelectionProbe />);

  expect(await screen.findByText('CSRT')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerCatalog);
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerAvailableTypes);
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerCurrentConfig);
  consoleWarn.mockRestore();
});

test('useTrackerSelection does not hide typed catalog auth failures with legacy fallback', async () => {
  const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerCatalog) {
      return Promise.reject({ response: { status: 401 }, message: 'unauthorized' });
    }
    return Promise.resolve({ data: {} });
  });

  render(<SelectionProbe />);

  await waitFor(() => {
    expect(screen.getByText('Error: unauthorized')).toBeInTheDocument();
  });
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerCatalog);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerAvailableTypes);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerCurrentConfig);
  consoleError.mockRestore();
});

test('useSwitchTracker prefers typed tracker-switch action', async () => {
  axios.post.mockImplementation((url, body) => {
    if (url === endpoints.trackerSwitchAction) {
      expect(body).toEqual(expect.objectContaining({
        source: 'dashboard',
        reason: 'switch_tracker',
        confirm: true,
        tracker_type: 'Gimbal',
        idempotency_key: expect.any(String),
        metadata: { ui: 'dashboard_tracker_selector' },
      }));
      return Promise.resolve({
        data: {
          status: 'success',
          result: {
            legacy_result: {
              action: 'tracker_switched',
              old_tracker: 'CSRT',
              new_tracker: 'Gimbal',
              requires_restart: false,
            },
          },
        },
      });
    }
    return Promise.reject(new Error(`unexpected legacy mutation: ${url}`));
  });

  render(<SwitchTrackerProbe />);
  fireEvent.click(screen.getByText('switch'));

  expect(await screen.findByText('result:true')).toBeInTheDocument();
  expect(screen.getByText('no-error')).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith(
    endpoints.trackerSwitchAction,
    expect.any(Object)
  );
  expect(axios.post).not.toHaveBeenCalledWith(
    endpoints.trackerSwitch,
    expect.anything()
  );
});

test('useSwitchTracker falls back to legacy switch when typed action is absent', async () => {
  const consoleWarn = jest.spyOn(console, 'warn').mockImplementation(() => {});
  axios.post.mockImplementation((url) => {
    if (url === endpoints.trackerSwitchAction) {
      return Promise.reject({ response: { status: 404 }, message: 'not found' });
    }
    if (url === endpoints.trackerSwitch) {
      return Promise.resolve({
        data: {
          status: 'success',
          requires_restart: true,
        },
      });
    }
    return Promise.reject(new Error(`unexpected mutation: ${url}`));
  });

  render(<SwitchTrackerProbe />);
  fireEvent.click(screen.getByText('switch'));

  expect(await screen.findByText('result:true')).toBeInTheDocument();
  expect(
    screen.getByText(
      'Tracker switched to Gimbal. Stop tracking and restart to activate the new tracker.'
    )
  ).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith(
    endpoints.trackerSwitchAction,
    expect.any(Object)
  );
  expect(axios.post).toHaveBeenCalledWith(
    endpoints.trackerSwitch,
    { tracker_type: 'Gimbal' }
  );
  consoleWarn.mockRestore();
});

test('useSwitchTracker does not hide typed action policy failures with legacy fallback', async () => {
  const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
  axios.post.mockImplementation((url) => {
    if (url === endpoints.trackerSwitchAction) {
      return Promise.reject({
        response: {
          status: 403,
          data: {
            detail: {
              message: 'forbidden',
              code: 'API_AUTH_FORBIDDEN',
            },
          },
        },
        message: 'forbidden',
      });
    }
    return Promise.resolve({ data: { status: 'success' } });
  });

  render(<SwitchTrackerProbe />);
  fireEvent.click(screen.getByText('switch'));

  expect(await screen.findByText('result:false')).toBeInTheDocument();
  expect(screen.getByText('forbidden')).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith(
    endpoints.trackerSwitchAction,
    expect.any(Object)
  );
  expect(axios.post).not.toHaveBeenCalledWith(
    endpoints.trackerSwitch,
    expect.anything()
  );
  consoleError.mockRestore();
});

test('useTrackerSelection does not hide typed catalog policy failures with legacy fallback', async () => {
  const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerCatalog) {
      return Promise.reject({ response: { status: 403 }, message: 'forbidden' });
    }
    return Promise.resolve({ data: {} });
  });

  render(<SelectionProbe />);

  await waitFor(() => {
    expect(screen.getByText('Error: forbidden')).toBeInTheDocument();
  });
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerCatalog);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerAvailableTypes);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerCurrentConfig);
  consoleError.mockRestore();
});

test('useTrackerSelection rejects malformed typed catalog objects without legacy fallback', async () => {
  const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerCatalog) {
      return Promise.resolve({ data: { status: 'available' } });
    }
    return Promise.resolve({ data: {} });
  });

  render(<SelectionProbe />);

  await waitFor(() => {
    expect(screen.getByText(
      'Error: Malformed typed tracker catalog response: missing tracking_catalog source.'
    )).toBeInTheDocument();
  });
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerCatalog);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerAvailableTypes);
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerCurrentConfig);
  consoleError.mockRestore();
});
