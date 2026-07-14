import { render, screen } from '@testing-library/react';
import OSDToggle, {
  formatOsdChoiceLabel,
  normalizeColorModes,
  normalizePresets,
} from './OSDToggle';
import { endpoints } from '../services/apiEndpoints';
import { apiFetch } from '../services/apiClient';

jest.mock('../services/apiClient', () => ({
  apiFetch: jest.fn(),
}));

const jsonResponse = (payload) => Promise.resolve({
  ok: true,
  json: async () => payload,
});

const installOsdResponses = ({ status, presets, colorModes }) => {
  apiFetch.mockImplementation((url) => {
    if (url === endpoints.osdStatus) {
      return jsonResponse(status);
    }
    if (url === endpoints.osdPresets) {
      return jsonResponse(presets);
    }
    if (url === endpoints.osdColorModes) {
      return jsonResponse(colorModes);
    }
    throw new Error(`Unexpected OSD test URL: ${url}`);
  });
};

afterEach(() => {
  jest.clearAllMocks();
});

test('normalizes OSD preset and color catalogs', () => {
  expect(normalizePresets([' professional ', '', 'debug', 'professional'])).toEqual([
    'professional',
    'debug',
  ]);
  expect(normalizeColorModes([' day ', null, 'night', 'day'])).toEqual([
    'day',
    'night',
  ]);
  expect(formatOsdChoiceLabel('full_telemetry')).toBe('Full Telemetry');
  expect(formatOsdChoiceLabel('field-ops')).toBe('Field Ops');
});

test('falls back cleanly when backend reports blank OSD selections', async () => {
  installOsdResponses({
    status: {
      enabled: true,
      configuration: {
        current_preset: '   ',
        color_mode: '',
      },
    },
    presets: {
      presets: [' professional ', '', 'debug', 'professional'],
      current: ' ',
    },
    colorModes: {
      available_modes: [' day ', '', 'night'],
      current: ' ',
    },
  });

  render(<OSDToggle />);

  expect(await screen.findByText('OSD Enabled')).toBeInTheDocument();
  expect(await screen.findByText(/Preset: Professional/)).toBeInTheDocument();
  expect(await screen.findByText(/Color: Day/)).toBeInTheDocument();
  expect(screen.queryByText(/Preset missing/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Color missing/)).not.toBeInTheDocument();
});

test('marks non-empty unknown OSD selections as missing instead of rendering empty controls', async () => {
  installOsdResponses({
    status: {
      enabled: true,
      configuration: {
        current_preset: 'field_ops',
        color_mode: 'ultraviolet',
      },
    },
    presets: {
      presets: ['professional', 'minimal'],
      current: '',
    },
    colorModes: {
      available_modes: ['day', 'night'],
      current: '',
    },
  });

  render(<OSDToggle />);

  expect(await screen.findByText('OSD Enabled')).toBeInTheDocument();
  expect(await screen.findByText(/Preset missing: Field Ops/)).toBeInTheDocument();
  expect(await screen.findByText(/Color missing: Ultraviolet/)).toBeInTheDocument();
});

test('keeps OSD status visible when optional color mode catalog is unavailable', async () => {
  apiFetch.mockImplementation((url) => {
    if (url === endpoints.osdStatus) {
      return jsonResponse({
        enabled: true,
        configuration: {
          current_preset: 'professional',
          color_mode: 'night',
        },
      });
    }
    if (url === endpoints.osdPresets) {
      return jsonResponse({
        presets: ['professional', 'debug'],
        current: 'professional',
      });
    }
    if (url === endpoints.osdColorModes) {
      return Promise.resolve({ ok: false, status: 503 });
    }
    throw new Error(`Unexpected OSD test URL: ${url}`);
  });

  render(<OSDToggle />);

  expect(await screen.findByText('OSD Enabled')).toBeInTheDocument();
  expect(await screen.findByText(/Preset: Professional/)).toBeInTheDocument();
  expect(await screen.findByText(/Color: Night/)).toBeInTheDocument();
});
