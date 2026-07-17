import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import TrackerSelector from './TrackerSelector';
import {
  useAvailableTrackers,
  useCurrentTracker,
  useSwitchTracker
} from '../hooks/useTrackerSchema';
import { useTrackerStatus } from '../hooks/useStatuses';

jest.mock('../hooks/useTrackerSchema', () => ({
  useAvailableTrackers: jest.fn(),
  useCurrentTracker: jest.fn(),
  useSwitchTracker: jest.fn()
}));

jest.mock('../hooks/useStatuses', () => ({
  useTrackerStatus: jest.fn()
}));

const availableTrackers = {
  available_trackers: {
    GimbalTracker: {
      ui_metadata: {
        display_name: 'External Gimbal',
        icon: 'T',
        short_description: 'External gimbal packets',
        performance_category: 'external'
      },
      description: 'Receives gimbal angle packets.',
      capabilities: ['external_input']
    },
    CSRTTracker: {
      ui_metadata: {
        display_name: 'CSRT',
        icon: 'C',
        short_description: 'Classic image tracker',
        performance_category: 'local'
      },
      description: 'Classic OpenCV tracker.'
    }
  }
};

const currentTracker = {
  status: 'configured',
  active: false,
  tracker_type: 'GimbalTracker',
  display_name: 'External Gimbal',
  icon: 'T',
  short_description: 'External gimbal packets',
  following_active: false
};

let currentTrackerMock;
let setCurrentTrackerFromHook;

const baseRuntimeStatus = {
  guidance: 'visible_output',
  label: 'Output Visible',
  chipLabel: 'Tracking: Visible',
  navLabel: 'Visible',
  color: 'info',
  detail: 'Tracker output is visible.',
  isTracking: false,
  activeTracking: false,
  hasOutput: true,
  usableForFollowing: false,
  dataIsStale: false,
  followLabel: 'Not For Follow',
  followColor: 'warning'
};

beforeEach(() => {
  currentTrackerMock = { ...currentTracker };
  useAvailableTrackers.mockReturnValue({
    trackers: availableTrackers,
    loading: false,
    error: null
  });
  useCurrentTracker.mockImplementation(() => {
    const [tracker, setTracker] = React.useState(currentTrackerMock);
    setCurrentTrackerFromHook = setTracker;
    return {
      currentTracker: tracker,
      loading: false,
      error: null
    };
  });
  useSwitchTracker.mockReturnValue({
    switchTracker: jest.fn(),
    switching: false,
    switchError: null
  });
  useTrackerStatus.mockReturnValue(baseRuntimeStatus);
});

afterEach(() => {
  jest.clearAllMocks();
});

test('shows visible tracker output without implying follower usability', () => {
  render(<TrackerSelector />);

  expect(screen.getByText('Output Visible')).toBeInTheDocument();
  expect(screen.getByText('Not For Follow')).toBeInTheDocument();
  expect(screen.getAllByText(/External Gimbal/).length).toBeGreaterThan(0);
});

test('shows stale runtime status from the typed tracker contract', () => {
  useTrackerStatus.mockReturnValue({
    ...baseRuntimeStatus,
    guidance: 'stale_output',
    label: 'Stale Output',
    chipLabel: 'Tracking: Stale',
    color: 'warning',
    activeTracking: true,
    dataIsStale: true
  });

  render(<TrackerSelector />);

  expect(screen.getByText('Stale Output')).toBeInTheDocument();
  expect(screen.getByText('Not For Follow')).toBeInTheDocument();
});

test('shows typed catalog error while preserving last known tracker data', () => {
  useAvailableTrackers.mockReturnValue({
    trackers: availableTrackers,
    loading: false,
    error: 'typed tracker catalog unavailable'
  });

  render(<TrackerSelector />);

  expect(screen.getByText('typed tracker catalog unavailable')).toBeInTheDocument();
  expect(screen.getByText('Output Visible')).toBeInTheDocument();
  expect(screen.getByText('Not For Follow')).toBeInTheDocument();
  expect(screen.getAllByText(/External Gimbal/).length).toBeGreaterThan(0);
});

test('shows typed current-tracker catalog error while preserving last known tracker data', () => {
  useCurrentTracker.mockReturnValue({
    currentTracker,
    loading: false,
    error: 'typed current tracker unavailable'
  });

  render(<TrackerSelector />);

  expect(screen.getByText('typed current tracker unavailable')).toBeInTheDocument();
  expect(screen.getByText('Output Visible')).toBeInTheDocument();
  expect(screen.getAllByText(/External Gimbal/).length).toBeGreaterThan(0);
});

test('resumes backend sync when pending selection converges before switch click', async () => {
  render(<TrackerSelector />);

  await waitFor(() => {
    expect(screen.getByRole('combobox')).toHaveTextContent('External Gimbal');
  });

  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(screen.getByRole('option', { name: /CSRT/ }));

  expect(screen.getByRole('combobox')).toHaveTextContent('CSRT');

  act(() => {
    setCurrentTrackerFromHook({
      ...currentTracker,
      tracker_type: 'CSRTTracker',
      display_name: 'CSRT',
      icon: 'C'
    });
  });

  await waitFor(() => {
    expect(screen.getByRole('combobox')).toHaveTextContent('CSRT');
  });

  act(() => {
    setCurrentTrackerFromHook({ ...currentTracker });
  });

  await waitFor(() => {
    expect(screen.getByRole('combobox')).toHaveTextContent('External Gimbal');
  });
});

test('submits the catalog key instead of the display label when switching', async () => {
  const switchTracker = jest.fn().mockResolvedValue(true);
  useSwitchTracker.mockReturnValue({
    switchTracker,
    switching: false,
    switchError: null
  });

  render(<TrackerSelector />);

  await waitFor(() => {
    expect(screen.getByRole('combobox')).toHaveTextContent('External Gimbal');
  });

  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(screen.getByRole('option', { name: /CSRT/ }));
  fireEvent.click(screen.getByRole('button', { name: /Switch Tracker/ }));

  await waitFor(() => {
    expect(switchTracker).toHaveBeenCalledWith('CSRTTracker');
  });
});

test('marks unavailable catalog entries as disabled choices', async () => {
  useAvailableTrackers.mockReturnValue({
    trackers: {
      available_trackers: {
        ...availableTrackers.available_trackers,
        SmartTracker: {
          available: false,
          unavailable_reason: 'AI packages are not installed',
          ui_metadata: {
            display_name: 'Smart Tracker',
            icon: 'S',
            short_description: 'AI tracker',
            performance_category: 'ai'
          },
        },
      },
    },
    loading: false,
    error: null
  });

  render(<TrackerSelector />);

  fireEvent.mouseDown(screen.getByRole('combobox'));
  const disabledOption = await screen.findByRole('option', { name: /Smart Tracker/ });

  expect(disabledOption).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByText('AI packages are not installed')).toBeInTheDocument();
});
