import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SectionEditor from './SectionEditor';
import { useConfigSection } from '../../hooks/useConfig';

jest.mock('../../hooks/useConfig', () => ({
  useConfigSection: jest.fn(),
}));

const mockUseResponsive = jest.fn();

jest.mock('../../hooks/useResponsive', () => ({
  useResponsive: () => mockUseResponsive(),
}));

const desktopResponsive = {
    isMobile: false,
    isTablet: false,
    isCompactDesktop: false,
    compactTable: false,
    touchTargetSize: 'small',
    buttonSize: 'small',
};

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

const mockSection = ({
  parameters = {},
  config,
  defaultConfig = config,
  schemaAvailable = true,
  schemaError = null,
  defaultError = null,
  mutationsAllowed = schemaAvailable,
}) => {
  useConfigSection.mockReturnValue({
    config,
    defaultConfig,
    schema: schemaAvailable ? {
      display_name: 'Video Source',
      parameters,
    } : null,
    schemaAvailable,
    schemaError,
    defaultError,
    mutationsAllowed,
    loading: false,
    error: null,
    updateParameter,
    revertParameter: jest.fn().mockResolvedValue(true),
    revertSection: jest.fn().mockResolvedValue(true),
    refetch: jest.fn(),
  });
};

beforeEach(() => {
  mockUseResponsive.mockReturnValue(desktopResponsive);
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

test('passes nested safety constraints to the specialized editor', () => {
  mockSection({
    config: { GlobalLimits: { MAX_VELOCITY_LATERAL: 1.5 } },
    parameters: {
      GlobalLimits: {
        type: 'object',
        required: ['MAX_VELOCITY_LATERAL'],
        additional_properties: false,
        properties: {
          MAX_VELOCITY_LATERAL: {
            type: 'float',
            default: 1.5,
            min: 0.125,
            max: 6.25,
            step: 0.125,
            unit: 'm/s',
          },
        },
      },
    },
  });

  render(<SectionEditor sectionName="Safety" autoSaveEnabled={false} />);

  expect(screen.getByRole('spinbutton')).toHaveAttribute('min', '0.125');
  expect(screen.getByRole('spinbutton')).toHaveAttribute('max', '6.25');
  expect(screen.getByRole('spinbutton')).toHaveAttribute('step', '0.125');
});

test('passes nested follower enums to the specialized editor', async () => {
  mockSection({
    config: { General: { LATERAL_GUIDANCE_MODE: 'coordinated_turn' } },
    parameters: {
      General: {
        type: 'object',
        properties: {
          LATERAL_GUIDANCE_MODE: {
            type: 'string',
            default: 'coordinated_turn',
            options: [
              { value: 'coordinated_turn', label: 'Coordinated turn' },
              { value: 'sideslip', label: 'Sideslip' },
            ],
          },
        },
      },
    },
  });

  render(<SectionEditor sectionName="Follower" autoSaveEnabled={false} />);

  fireEvent.mouseDown(screen.getByRole('combobox'));
  expect(await screen.findByRole('option', { name: 'Sideslip' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: /direct/i })).not.toBeInTheDocument();
});

test('shows current values read-only and disables mutations when schema loading failed', () => {
  mockSection({
    config: { LEGACY_VALUE: 'preserved' },
    schemaAvailable: false,
    schemaError: 'schema request failed',
  });

  render(<SectionEditor sectionName="VideoSource" />);

  expect(screen.getByDisplayValue('preserved')).toBeDisabled();
  expect(screen.getByText(/Current values are shown read-only/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Revert All/i })).toBeDisabled();
  expect(updateParameter).not.toHaveBeenCalled();
});

test('closed enums do not offer custom values and lock undeclared current values', async () => {
  mockSection({
    config: { MODE: 'legacy' },
    parameters: {
      MODE: {
        type: 'string',
        options: [{ value: 'safe', label: 'Safe' }],
      },
    },
  });

  render(<SectionEditor sectionName="VideoSource" />);

  expect(screen.getByRole('combobox')).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByText('Needs migration')).toBeInTheDocument();
  expect(screen.queryByText(/Enter custom value/i)).not.toBeInTheDocument();
});

test('an enum exposes custom input only when the schema explicitly permits it', async () => {
  mockSection({
    config: { MODE: 'safe' },
    parameters: {
      MODE: {
        type: 'string',
        allow_custom_values: true,
        options: [{ value: 'safe', label: 'Safe' }],
      },
    },
  });

  render(<SectionEditor sectionName="VideoSource" autoSaveEnabled={false} />);
  fireEvent.mouseDown(screen.getByRole('combobox'));

  expect(await screen.findByRole('option', { name: /Enter custom value/i })).toBeInTheDocument();
});

test('autosave serializes in-flight writes and leaves the newest value last', async () => {
  let resolveFirst;
  updateParameter
    .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
    .mockResolvedValueOnce({ success: true, saved: true });
  mockSection({
    config: { ENABLED: false },
    parameters: { ENABLED: { type: 'boolean', default: false } },
  });

  render(<SectionEditor sectionName="VideoSource" autoSaveEnabled />);
  const toggle = screen.getByRole('checkbox');
  fireEvent.click(toggle);

  await waitFor(() => expect(updateParameter).toHaveBeenCalledTimes(1), { timeout: 1000 });
  fireEvent.click(toggle);

  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 300));
  });
  expect(updateParameter).toHaveBeenCalledTimes(1);

  await act(async () => {
    resolveFirst({ success: true, saved: true });
  });
  await waitFor(() => expect(updateParameter).toHaveBeenCalledTimes(2));
  expect(updateParameter.mock.calls).toEqual([
    ['ENABLED', true],
    ['ENABLED', false],
  ]);
});

test.each([
  ['mobile', { isMobile: true, isTablet: false, isCompactDesktop: false }],
  ['tablet', { isMobile: false, isTablet: true, isCompactDesktop: false }],
])('uses touch-friendly cards on %s viewports', (_name, viewport) => {
  mockUseResponsive.mockReturnValue({ ...desktopResponsive, ...viewport, touchTargetSize: 'medium', buttonSize: 'medium' });
  mockSection({
    config: { LABEL: 'camera' },
    parameters: { LABEL: { type: 'string', default: 'camera' } },
  });

  render(<SectionEditor sectionName="VideoSource" />);

  expect(screen.getByRole('button', { name: 'Details' })).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.getByDisplayValue('camera')).toBeInTheDocument();
});
