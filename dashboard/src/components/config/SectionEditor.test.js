import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SectionEditor from './SectionEditor';
import { useConfigSection } from '../../hooks/useConfig';

jest.mock('../../hooks/useConfig', () => ({
  useConfigSection: jest.fn(),
}));

jest.mock('../../hooks/useResponsive', () => ({
  useResponsive: () => ({
    isMobile: false,
    isTablet: false,
    isCompactDesktop: false,
    compactTable: false,
    touchTargetSize: 'small',
    buttonSize: 'small',
  }),
}));

jest.mock('../../hooks/useConfigGlobalState', () => ({
  useConfigGlobalState: () => ({
    registerUnsavedChange: jest.fn(),
    markSectionSaving: jest.fn(),
    markParamSaved: jest.fn(),
    markSaveError: jest.fn(),
    refreshModifiedCount: jest.fn(),
    clearSectionChanges: jest.fn(),
  }),
}));

const updateParameter = jest.fn();

const mockSection = ({ parameters, config, defaultConfig = config }) => {
  useConfigSection.mockReturnValue({
    config,
    defaultConfig,
    schema: {
      display_name: 'Video Source',
      parameters,
    },
    loading: false,
    error: null,
    updateParameter,
    revertParameter: jest.fn().mockResolvedValue(true),
    revertSection: jest.fn().mockResolvedValue(true),
    refetch: jest.fn(),
  });
};

beforeEach(() => {
  updateParameter.mockResolvedValue({ success: true, saved: true });
});

afterEach(() => {
  jest.clearAllMocks();
});

test('manual mode keeps enum changes local until Save All', async () => {
  mockSection({
    config: { VIDEO_SOURCE_TYPE: 'VIDEO_FILE' },
    parameters: {
      VIDEO_SOURCE_TYPE: {
        type: 'string',
        default: 'VIDEO_FILE',
        reload_tier: 'system_restart',
        options: [
          { value: 'VIDEO_FILE', label: 'Video file' },
          { value: 'USB_CAMERA', label: 'USB camera' },
        ],
      },
    },
  });

  render(<SectionEditor sectionName="VideoSource" autoSaveEnabled={false} />);

  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name: /USB camera/ }));

  expect(updateParameter).not.toHaveBeenCalled();
  expect(await screen.findByText(/Manual save mode/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Save All/ }));

  await waitFor(() => {
    expect(updateParameter).toHaveBeenCalledWith('VIDEO_SOURCE_TYPE', 'USB_CAMERA');
  });
});

test('auto-save mode persists enum changes immediately', async () => {
  mockSection({
    config: { VIDEO_SOURCE_TYPE: 'VIDEO_FILE' },
    parameters: {
      VIDEO_SOURCE_TYPE: {
        type: 'string',
        default: 'VIDEO_FILE',
        options: [
          { value: 'VIDEO_FILE', label: 'Video file' },
          { value: 'USB_CAMERA', label: 'USB camera' },
        ],
      },
    },
  });

  render(<SectionEditor sectionName="VideoSource" autoSaveEnabled />);

  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name: /USB camera/ }));

  await waitFor(() => {
    expect(updateParameter).toHaveBeenCalledWith('VIDEO_SOURCE_TYPE', 'USB_CAMERA');
  });
});

test('manual mode keeps boolean changes local until Save All', async () => {
  mockSection({
    config: { USE_GSTREAMER: false },
    parameters: {
      USE_GSTREAMER: {
        type: 'boolean',
        default: false,
        reload_tier: 'system_restart',
      },
    },
  });

  render(<SectionEditor sectionName="VideoSource" autoSaveEnabled={false} />);

  fireEvent.click(screen.getByRole('checkbox'));

  expect(updateParameter).not.toHaveBeenCalled();
  expect(await screen.findByText(/Manual save mode/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Save All/ }));

  await waitFor(() => {
    expect(updateParameter).toHaveBeenCalledWith('USE_GSTREAMER', true);
  });
});
