import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import SyncWithDefaultsDialog from './SyncWithDefaultsDialog';

const EMPTY_COUNTS = { new: 0, changed: 0, retired: 0, extensions: 0, actionable: 0 };
const DEFAULT_META = {
  baselineAvailable: true,
  baselineSavedAt: null,
  schemaVersion: '1.1.0',
  retirementRegistryVersion: 1,
};

let defaultsSync;

const testTheme = createTheme({
  transitions: {
    duration: {
      shortest: 0,
      shorter: 0,
      short: 0,
      standard: 0,
      complex: 0,
      enteringScreen: 0,
      leavingScreen: 0,
    },
  },
  components: {
    MuiButtonBase: {
      defaultProps: { disableRipple: true },
    },
    MuiDialog: {
      defaultProps: { transitionDuration: 0 },
    },
  },
});

const mockSyncState = (overrides = {}) => {
  defaultsSync = {
    newParameters: [],
    changedDefaults: [],
    registeredRetirements: [],
    unknownExtensions: [],
    counts: EMPTY_COUNTS,
    meta: DEFAULT_META,
    loading: false,
    error: null,
    reportAvailable: true,
    planning: false,
    applying: false,
    refresh: jest.fn(),
    buildOperationsFromSelections: jest.fn(() => []),
    previewOperations: jest.fn(),
    applyOperations: jest.fn(),
    ...overrides,
  };
  return defaultsSync;
};

const renderDialog = (props = {}) => render(
  <ThemeProvider theme={testTheme}>
    <SyncWithDefaultsDialog
      open
      onClose={jest.fn()}
      defaultsSync={defaultsSync}
      {...props}
    />
  </ThemeProvider>
);

const mockRetirementState = () => {
  const operations = [{
    op_type: 'REMOVE_RETIRED',
    path: ['GStreamer', 'OLD_KEY'],
  }];
  const previewOperations = jest.fn().mockResolvedValue({
    success: true,
    plan: {
      valid: true,
      plan_digest: 'd'.repeat(64),
      summary: { applicable: 1, skipped: 0 },
      warnings: [],
      errors: [],
    },
  });
  const applyOperations = jest.fn().mockResolvedValue({
    success: true,
    result: { applied_count: 1, skipped_count: 0, applied_operations: [] },
  });
  mockSyncState({
    registeredRetirements: [{
      id: 'retire-old-key',
      path: ['GStreamer', 'OLD_KEY'],
      section: 'GStreamer',
      parameter: 'OLD_KEY',
      reason: 'Replaced by the output pipeline',
      replacement: null,
    }],
    counts: { new: 0, changed: 0, retired: 1, extensions: 0, actionable: 1 },
    buildOperationsFromSelections: jest.fn((selection) => (
      selection.selectedRetired.length > 0 ? operations : []
    )),
    previewOperations,
    applyOperations,
  });
  return { operations, previewOperations, applyOperations };
};

describe('SyncWithDefaultsDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSyncState();
  });

  it('auto-opens retirements and leaves destructive changes unselected', async () => {
    mockRetirementState();

    renderDialog({ onMessage: jest.fn() });

    const retiredTab = screen.getByRole('tab', { name: /Retired/i });
    await waitFor(() => expect(retiredTab).toHaveAttribute('aria-selected', 'true'));

    const retirementCheckbox = screen.getByRole('checkbox', { name: /GStreamer\.OLD_KEY/i });
    expect(retirementCheckbox).not.toBeChecked();
    expect(screen.getByRole('button', { name: /Apply Previewed/i })).toBeDisabled();
  });

  it('invalidates the preview digest whenever retirement selection changes', async () => {
    mockRetirementState();
    renderDialog({ onMessage: jest.fn() });

    const retirementCheckbox = await screen.findByRole('checkbox', { name: /GStreamer\.OLD_KEY/i });

    fireEvent.click(retirementCheckbox);
    fireEvent.click(screen.getByRole('button', { name: /^Preview$/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply Previewed/i })).toBeEnabled();
    });

    fireEvent.click(retirementCheckbox);
    fireEvent.click(retirementCheckbox);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply Previewed/i })).toBeDisabled();
    });
  });

  it('applies only the operations covered by the current preview digest', async () => {
    const { operations, applyOperations } = mockRetirementState();
    renderDialog({ onMessage: jest.fn() });

    fireEvent.click(await screen.findByRole('checkbox', { name: /GStreamer\.OLD_KEY/i }));

    fireEvent.click(screen.getByRole('button', { name: /^Preview$/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply Previewed/i })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Apply Previewed/i }));

    await waitFor(() => {
      expect(applyOperations).toHaveBeenCalledWith(operations, 'd'.repeat(64));
    });
  });

  it('renders report failures as unavailable instead of a green clean state', () => {
    mockSyncState({
      reportAvailable: false,
      error: 'Unsupported Config Sync contract version 1',
    });

    renderDialog();

    expect(screen.getByText(/Config migration status unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/Unsupported Config Sync contract version 1/i)).toBeInTheDocument();
    expect(screen.queryByText(/No config migration is required/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Preview$/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Apply Previewed/i })).toBeDisabled();
  });

  it('shows root paths and every preview warning individually', async () => {
    const operations = [{ op_type: 'ADD_NEW', path: ['ROOT_SETTING'] }];
    mockSyncState({
      newParameters: [
        {
          path: ['ROOT_SETTING'],
          parameter: 'ROOT_SETTING',
          default_value: true,
        },
      ],
      counts: { new: 1, changed: 0, retired: 0, extensions: 0, actionable: 1 },
      buildOperationsFromSelections: jest.fn(() => operations),
      previewOperations: jest.fn().mockResolvedValue({
        success: true,
        plan: {
          valid: true,
          plan_digest: 'e'.repeat(64),
          summary: { applicable: 1, skipped: 0 },
          warnings: [
            { index: 0, warning: 'Runtime reload will be required' },
            { index: 1, warning: 'Verify the root-level consumer' },
          ],
          errors: [],
        },
      }),
    });

    renderDialog();

    expect(screen.getByText('Root')).toBeInTheDocument();
    expect(screen.getByText('ROOT_SETTING')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Preview$/i }));

    const warningList = await screen.findByRole('list', { name: /Preview warnings/i });
    expect(within(warningList).getByText('Runtime reload will be required')).toBeInTheDocument();
    expect(within(warningList).getByText('Verify the root-level consumer')).toBeInTheDocument();
  });

  it('keeps dialog actions wrapping without horizontal overflow', () => {
    mockSyncState({ reportAvailable: false, error: 'Unavailable' });
    renderDialog();

    expect(screen.getByTestId('config-sync-actions')).toHaveStyle({
      flexWrap: 'wrap',
      overflowX: 'hidden',
    });
  });

  it('does not claim a missing defaults baseline was initialized by a read', () => {
    mockSyncState({
      newParameters: [
        {
          path: ['VideoSource', 'NEW_SETTING'],
          section: 'VideoSource',
          parameter: 'NEW_SETTING',
          default_value: true,
        },
      ],
      counts: { new: 1, changed: 0, retired: 0, extensions: 0, actionable: 1 },
      meta: { ...DEFAULT_META, baselineAvailable: false },
    });

    renderDialog({ onMessage: jest.fn() });

    fireEvent.click(screen.getByRole('tab', { name: /Changed/i }));
    expect(screen.getByText(/No pre-update defaults baseline is available/i)).toBeInTheDocument();
    expect(screen.queryByText(/has been initialized/i)).not.toBeInTheDocument();
  });

  it('refreshes its shared report owner whenever the dialog opens', () => {
    const state = mockSyncState();

    renderDialog();

    expect(state.refresh).toHaveBeenCalledTimes(1);
  });

  it('keeps extension-only status visible when no migration action exists', () => {
    mockSyncState({
      unknownExtensions: [{ path: ['Plugin', 'PRIVATE_SETTING'] }],
      counts: { ...EMPTY_COUNTS, extensions: 1 },
    });

    renderDialog();

    expect(screen.getByText(/1 unmanaged extension path/i)).toBeInTheDocument();
  });

  it('invalidates a preview and refreshes after an apply failure', async () => {
    const operations = [{ op_type: 'ADD_NEW', path: ['ROOT_SETTING'] }];
    const state = mockSyncState({
      newParameters: [{ path: ['ROOT_SETTING'], default_value: true }],
      counts: { new: 1, changed: 0, retired: 0, extensions: 0, actionable: 1 },
      buildOperationsFromSelections: jest.fn(() => operations),
      previewOperations: jest.fn().mockResolvedValue({
        success: true,
        plan: {
          valid: true,
          plan_digest: 'f'.repeat(64),
          summary: { requested: 1, applicable: 1, skipped: 0 },
          warnings: [],
          errors: [],
        },
      }),
      applyOperations: jest.fn().mockResolvedValue({
        success: false,
        error: 'Config migration sources changed after preview',
      }),
    });

    renderDialog({ onMessage: jest.fn() });
    fireEvent.click(screen.getByRole('button', { name: /^Preview$/i }));
    await waitFor(() => expect(
      screen.getByRole('button', { name: /Apply Previewed/i })
    ).toBeEnabled());

    fireEvent.click(screen.getByRole('button', { name: /Apply Previewed/i }));

    await waitFor(() => expect(
      screen.getByRole('button', { name: /Apply Previewed/i })
    ).toBeDisabled());
    expect(state.applyOperations).toHaveBeenCalledTimes(1);
    expect(state.refresh).toHaveBeenCalledTimes(2);
  });

  it('discards an in-flight preview when bulk selection changes', async () => {
    let resolvePreview;
    const previewOperations = jest.fn(() => new Promise((resolve) => {
      resolvePreview = resolve;
    }));
    mockSyncState({
      newParameters: [{ path: ['ROOT_SETTING'], default_value: true }],
      counts: { new: 1, changed: 0, retired: 0, extensions: 0, actionable: 1 },
      buildOperationsFromSelections: jest.fn((selection) => (
        selection.selectedNew.length > 0
          ? [{ op_type: 'ADD_NEW', path: ['ROOT_SETTING'] }]
          : []
      )),
      previewOperations,
    });

    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: /^Preview$/i }));
    await waitFor(() => expect(previewOperations).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: /Select None/i }));
    await act(async () => {
      resolvePreview({
        success: true,
        plan: {
          valid: true,
          plan_digest: 'a'.repeat(64),
          summary: { requested: 1, applicable: 1, skipped: 0 },
          warnings: [],
          errors: [],
        },
      });
    });

    expect(screen.queryByText(/Preview: 1 applicable/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Apply Previewed/i })).toBeDisabled();
  });

  it('prevents closing while a preview or apply operation is active', () => {
    const onClose = jest.fn();
    mockSyncState({ applying: true });

    renderDialog({ onClose });

    expect(screen.getByRole('button', { name: /^Close$/i })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});
