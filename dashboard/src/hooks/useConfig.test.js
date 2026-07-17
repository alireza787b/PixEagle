import { act, renderHook, waitFor } from '@testing-library/react';
import axios from '../services/apiClient';
import { useConfigSchema, useConfigSection } from './useConfig';

jest.mock('../services/apiClient', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    put: jest.fn(),
    post: jest.fn(),
    isCancel: jest.fn(() => false),
  },
}));

const validSectionSchema = {
  display_name: 'Video Source',
  parameters: {
    MODE: { type: 'string', default: 'file' },
  },
};

beforeEach(() => {
  jest.clearAllMocks();
});

test('fetches current/default/schema independently and preserves current values on schema failure', async () => {
  axios.get
    .mockResolvedValueOnce({ data: { success: true, config: { MODE: 'camera' } } })
    .mockResolvedValueOnce({ data: { success: true, config: { MODE: 'file' } } })
    .mockRejectedValueOnce(new Error('schema offline'));

  const { result } = renderHook(() => useConfigSection('VideoSource'));

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(axios.get).toHaveBeenCalledTimes(3);
  expect(result.current.config).toEqual({ MODE: 'camera' });
  expect(result.current.defaultConfig).toEqual({ MODE: 'file' });
  expect(result.current.error).toBeNull();
  expect(result.current.schemaAvailable).toBe(false);
  expect(result.current.schemaError).toBe('schema offline');
  expect(result.current.mutationsAllowed).toBe(false);

  let mutationResult;
  await act(async () => {
    mutationResult = await result.current.updateParameter('MODE', 'file');
  });
  expect(mutationResult).toMatchObject({ success: false, saved: false });
  expect(axios.put).not.toHaveBeenCalled();
});

test('treats a malformed successful schema response as read-only', async () => {
  axios.get
    .mockResolvedValueOnce({ data: { success: true, config: { MODE: 'camera' } } })
    .mockResolvedValueOnce({ data: { success: true, config: { MODE: 'file' } } })
    .mockResolvedValueOnce({ data: { success: true, schema: { parameters: { MODE: {} } } } });

  const { result } = renderHook(() => useConfigSection('VideoSource'));

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.config).toEqual({ MODE: 'camera' });
  expect(result.current.schema).toBeNull();
  expect(result.current.schemaAvailable).toBe(false);
  expect(result.current.schemaError).toMatch(/missing or unsupported type/i);
  expect(result.current.revertSection).toBeDefined();

  let reverted;
  await act(async () => {
    reverted = await result.current.revertSection();
  });
  expect(reverted).toBe(false);
  expect(axios.post).not.toHaveBeenCalled();
});

test('keeps a valid schema editable when only defaults fail', async () => {
  axios.get
    .mockResolvedValueOnce({ data: { success: true, config: { MODE: 'camera' } } })
    .mockRejectedValueOnce(new Error('defaults offline'))
    .mockResolvedValueOnce({ data: { success: true, schema: validSectionSchema } });
  axios.put.mockResolvedValueOnce({ data: { success: true, saved: true } });

  const { result } = renderHook(() => useConfigSection('VideoSource'));

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.defaultConfig).toEqual({});
  expect(result.current.defaultError).toBe('defaults offline');
  expect(result.current.schemaAvailable).toBe(true);
  expect(result.current.mutationsAllowed).toBe(true);

  await act(async () => {
    await result.current.updateParameter('MODE', 'file');
  });
  expect(axios.put).toHaveBeenCalledTimes(1);
});

test('full schema hook fails closed on malformed section contracts', async () => {
  axios.get.mockResolvedValueOnce({
    data: {
      success: true,
      schema: { sections: { Broken: { parameters: { VALUE: {} } } } },
    },
  });

  const { result } = renderHook(() => useConfigSchema());

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.schema).toBeNull();
  expect(result.current.error).toMatch(/Section Broken/);
});

test('full schema hook exposes only a completely validated schema', async () => {
  const schema = {
    sections: {
      VideoSource: validSectionSchema,
    },
  };
  axios.get.mockResolvedValueOnce({ data: { success: true, schema } });

  const { result } = renderHook(() => useConfigSchema());

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.schema).toEqual(schema);
  expect(result.current.error).toBeNull();
});
