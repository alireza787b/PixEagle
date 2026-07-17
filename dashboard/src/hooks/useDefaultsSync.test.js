import { act, renderHook, waitFor } from '@testing-library/react';
import apiClient from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import {
  CONFIG_SYNC_CONTRACT_VERSION,
  getConfigSyncItemKey,
  getConfigSyncItemPath,
  useDefaultsSync,
} from './useDefaultsSync';

jest.mock('../services/apiClient', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

const report = {
  success: true,
  contract_version: CONFIG_SYNC_CONTRACT_VERSION,
  new_parameters: [
    {
      path: ['ROOT_SETTING'],
      parameter: 'ROOT_SETTING',
      default_value: true,
    },
  ],
  changed_defaults: [
    {
      path: ['VideoSource', 'EOF_POLICY'],
      section: 'VideoSource',
      parameter: 'EOF_POLICY',
      old_default: 'STOP',
      new_default: 'LOOP',
    },
  ],
  registered_retirements: [
    {
      id: 'retire-old-key',
      path: ['VideoSource', 'OLD_KEY'],
      section: 'VideoSource',
      parameter: 'OLD_KEY',
      reason: 'Replaced',
      replacement: null,
    },
  ],
  unknown_extensions: [
    { path: ['Plugin', 'PRIVATE_SETTING'], value_type: 'string' },
  ],
  counts: { new: 1, changed: 1, retired: 1, extensions: 1, actionable: 3 },
  baseline_available: true,
  schema_version: '1.1.0',
  retirement_registry_version: 1,
};

describe('useDefaultsSync', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    apiClient.get.mockResolvedValue({ data: report });
  });

  it('builds canonical path operations and sends the v2 contract', async () => {
    apiClient.post
      .mockResolvedValueOnce({
        data: {
          success: true,
          contract_version: CONFIG_SYNC_CONTRACT_VERSION,
          plan: {
            contract_version: CONFIG_SYNC_CONTRACT_VERSION,
            valid: true,
            plan_digest: 'd'.repeat(64),
            operations: [
              { op_type: 'ADD_NEW', path: ['ROOT_SETTING'] },
              { op_type: 'ADOPT_DEFAULT', path: ['VideoSource', 'EOF_POLICY'] },
              { op_type: 'REMOVE_RETIRED', path: ['VideoSource', 'OLD_KEY'] },
            ],
            summary: { requested: 3, applicable: 3, skipped: 0 },
            warnings: [],
            errors: [],
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          success: true,
          contract_version: CONFIG_SYNC_CONTRACT_VERSION,
          applied_count: 3,
          skipped_count: 0,
          applied_operations: [
            { op_type: 'ADD_NEW', path: ['ROOT_SETTING'] },
            { op_type: 'ADOPT_DEFAULT', path: ['VideoSource', 'EOF_POLICY'] },
            { op_type: 'REMOVE_RETIRED', path: ['VideoSource', 'OLD_KEY'] },
          ],
          skipped_operations: [],
          plan_digest: 'd'.repeat(64),
        },
      });

    const { result } = renderHook(() => useDefaultsSync());
    await waitFor(() => expect(result.current.reportAvailable).toBe(true));

    const operations = result.current.buildOperationsFromSelections({
      selectedNew: [getConfigSyncItemKey(report.new_parameters[0])],
      selectedChanged: [getConfigSyncItemKey(report.changed_defaults[0])],
      selectedRetired: [getConfigSyncItemKey(report.registered_retirements[0])],
    });
    expect(operations).toEqual([
      { op_type: 'ADD_NEW', path: ['ROOT_SETTING'] },
      { op_type: 'ADOPT_DEFAULT', path: ['VideoSource', 'EOF_POLICY'] },
      { op_type: 'REMOVE_RETIRED', path: ['VideoSource', 'OLD_KEY'] },
    ]);
    expect(result.current.unknownExtensions).toEqual(report.unknown_extensions);

    let preview;
    await act(async () => {
      preview = await result.current.previewOperations(operations);
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      endpoints.configDefaultsSyncPlan,
      { contract_version: CONFIG_SYNC_CONTRACT_VERSION, operations }
    );

    await act(async () => {
      await result.current.applyOperations(operations, preview.plan.plan_digest);
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      endpoints.configDefaultsSyncApply,
      {
        contract_version: CONFIG_SYNC_CONTRACT_VERSION,
        operations,
        plan_digest: 'd'.repeat(64),
        confirm: true,
      }
    );
  });

  it('clears stale report data as soon as a refresh starts', async () => {
    const { result } = renderHook(() => useDefaultsSync());
    await waitFor(() => expect(result.current.reportAvailable).toBe(true));

    let resolveRefresh;
    apiClient.get.mockImplementationOnce(() => new Promise((resolve) => {
      resolveRefresh = resolve;
    }));

    let refreshPromise;
    act(() => {
      refreshPromise = result.current.refresh();
    });

    expect(result.current.loading).toBe(true);
    expect(result.current.reportAvailable).toBe(false);
    expect(result.current.newParameters).toEqual([]);
    expect(result.current.counts.actionable).toBe(0);

    await act(async () => {
      resolveRefresh({
        data: {
          success: false,
          contract_version: CONFIG_SYNC_CONTRACT_VERSION,
          error: 'Report generation failed',
        },
      });
      await refreshPromise;
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.reportAvailable).toBe(false);
    expect(result.current.error).toBe('Report generation failed');
  });

  it.each([
    [
      'a non-success payload',
      {
        ...report,
        success: false,
        error: 'Backend refused the report',
      },
      'Backend refused the report',
    ],
    [
      'an unsupported contract',
      {
        ...report,
        contract_version: 1,
      },
      /requires version 2/i,
    ],
  ])('marks the report unavailable for %s', async (label, payload, expectedError) => {
    apiClient.get.mockResolvedValueOnce({ data: payload });
    const { result } = renderHook(() => useDefaultsSync());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.reportAvailable).toBe(false);
    expect(result.current.newParameters).toEqual([]);
    expect(result.current.hasSyncItems).toBe(false);
    expect(result.current.error).toEqual(expect.stringMatching(expectedError));
  });

  it('rejects non-v2 preview and apply payloads', async () => {
    apiClient.post
      .mockResolvedValueOnce({
        data: {
          success: true,
          contract_version: 1,
          plan: { valid: true, plan_digest: 'a'.repeat(64) },
        },
      })
      .mockResolvedValueOnce({
        data: {
          success: false,
          contract_version: CONFIG_SYNC_CONTRACT_VERSION,
          error: 'Apply was rejected',
        },
      });
    const { result } = renderHook(() => useDefaultsSync());
    await waitFor(() => expect(result.current.reportAvailable).toBe(true));

    const operations = [{ op_type: 'ADD_NEW', path: ['ROOT_SETTING'], value: true }];
    let preview;
    let apply;
    await act(async () => {
      preview = await result.current.previewOperations(operations);
      apply = await result.current.applyOperations(operations, 'a'.repeat(64));
    });

    expect(preview).toEqual(expect.objectContaining({ success: false }));
    expect(preview.error).toMatch(/requires version 2/i);
    expect(apply).toEqual({ success: false, error: 'Apply was rejected' });
  });

  it('rejects display-only legacy fields as canonical paths', () => {
    const legacyDisplayItem = { section: 'VideoSource', parameter: 'VIDEO_FILE' };
    expect(getConfigSyncItemPath(legacyDisplayItem)).toEqual([]);
    expect(getConfigSyncItemKey(legacyDisplayItem)).toBe('');
  });

  it('uses collision-safe keys when path components contain dots', () => {
    const nested = { path: ['Section.with.dot', 'VALUE'] };
    const different = { path: ['Section', 'with.dot.VALUE'] };

    expect(getConfigSyncItemKey(nested)).not.toBe(getConfigSyncItemKey(different));
  });

  it('rejects malformed successful preview and apply payloads', async () => {
    apiClient.post
      .mockResolvedValueOnce({
        data: {
          success: true,
          contract_version: CONFIG_SYNC_CONTRACT_VERSION,
          plan: {
            contract_version: CONFIG_SYNC_CONTRACT_VERSION,
            valid: true,
            plan_digest: 'b'.repeat(64),
            operations: [],
            summary: { requested: 1, applicable: 0, skipped: 0 },
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          success: true,
          contract_version: CONFIG_SYNC_CONTRACT_VERSION,
          applied_count: 1,
          skipped_count: 0,
          applied_operations: [],
          skipped_operations: [],
          plan_digest: 'b'.repeat(64),
        },
      });
    const { result } = renderHook(() => useDefaultsSync());
    await waitFor(() => expect(result.current.reportAvailable).toBe(true));

    const operations = [{ op_type: 'ADD_NEW', path: ['ROOT_SETTING'] }];
    let preview;
    let apply;
    await act(async () => {
      preview = await result.current.previewOperations(operations);
      apply = await result.current.applyOperations(operations, 'b'.repeat(64));
    });

    expect(preview.error).toMatch(/malformed operation details/i);
    expect(apply.error).toMatch(/counts do not match/i);
  });

  it('ignores an older report response that completes after a newer refresh', async () => {
    const { result } = renderHook(() => useDefaultsSync());
    await waitFor(() => expect(result.current.reportAvailable).toBe(true));

    let resolveOlder;
    let resolveNewer;
    apiClient.get
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOlder = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNewer = resolve; }));

    let olderPromise;
    let newerPromise;
    act(() => {
      olderPromise = result.current.refresh();
      newerPromise = result.current.refresh();
    });
    const newerReport = {
      ...report,
      new_parameters: [],
      counts: { ...report.counts, new: 0, actionable: 2 },
    };
    await act(async () => {
      resolveNewer({ data: newerReport });
      await newerPromise;
    });
    expect(result.current.newParameters).toEqual([]);

    await act(async () => {
      resolveOlder({ data: report });
      await olderPromise;
    });
    expect(result.current.newParameters).toEqual([]);
    expect(result.current.counts.actionable).toBe(2);
  });

  it('marks a v2 report unavailable when an item lacks a canonical path', async () => {
    apiClient.get.mockResolvedValueOnce({
      data: {
        ...report,
        new_parameters: [{ parameter: 'LEGACY_ONLY', default_value: true }],
        counts: { ...report.counts, new: 1, actionable: 3 },
      },
    });
    const { result } = renderHook(() => useDefaultsSync());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.reportAvailable).toBe(false);
    expect(result.current.error).toMatch(/non-canonical config path/i);
  });
});
