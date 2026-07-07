import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ValidationPage from './ValidationPage';
import { apiFetch } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

let mockCanReadValidation = true;

jest.mock('../services/apiClient', () => ({
  apiFetch: jest.fn(),
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: (scope) => mockCanReadValidation && scope === 'debug:read',
  }),
}));

const jsonResponse = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
});

const statusPayload = (latestRun = {}) => ({
  schema_version: 1,
  source: 'pixeagle_sitl_validation_status',
  profile: 'official_px4_sih',
  default_artifact_root: 'reports/sitl',
  injections_enabled: false,
  raw_injection_controls_exposed: false,
  plan: {
    name: 'phase2_follower_validation',
    title: 'Phase 2 PX4-In-Loop Follower Validation',
    level: 'L2',
    source: 'tools/sitl_plans/phase2_follower_validation.json',
    hash: 'abc123',
    scenario_count: 9,
    required_phase2_scenarios_present: ['offboard_entry'],
    required_phase2_scenarios_missing: [],
    evidence_artifact_count: 27,
    routing_provider: 'mavlink-anywhere',
    px4_image: 'px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01',
    px4_model: 'sihsim_quadx',
  },
  commands: [
    {
      label: 'SIH dry run',
      command: 'make sitl-sih-dry-run',
      mode: 'dry_run',
      starts_processes: false,
      writes_artifacts: false,
      requires_operator_stack: false,
      claim_boundary: 'Validates the checked-in L2 plan only.',
    },
    {
      label: 'Probe prepared stack',
      command: 'make sitl-sih-probe',
      mode: 'probe_only',
      starts_processes: false,
      writes_artifacts: true,
      requires_operator_stack: true,
      claim_boundary: 'Collects evidence from an already prepared stack.',
    },
    {
      label: 'PX4-only SIH container',
      command: 'make sitl-sih-execute-px4',
      mode: 'execute_px4',
      starts_processes: true,
      writes_artifacts: true,
      requires_operator_stack: true,
      claim_boundary: 'Starts only the harness-owned official PX4 SIH container.',
    },
  ],
  latest_run: {
    available: true,
    run_id: 'sih-demo-run',
    mode: 'execute',
    result: 'incomplete',
    result_reason: 'One or more required artifacts are missing.',
    artifact_dir: 'reports/sitl/sih-demo-run',
    updated_at: '2026-07-07T01:05:01+00:00',
    scenario_execution_enabled: false,
    control_actions_allowed: false,
    missing_or_placeholder_count: 2,
    missing_or_placeholder_artifacts: [
      'probes/pixeagle_status.json',
      'px4/tlog_manifest.json',
    ],
    missing_or_placeholder_truncated: false,
    semantic_failures: ['mavlink_anywhere_required_outputs'],
    artifact_content_failures: [],
    ...latestRun,
  },
  claim_boundary: 'PixEagle SIH/SITL training metadata only.',
  timestamp: 1783386300,
});

beforeEach(() => {
  mockCanReadValidation = true;
  apiFetch.mockReset();
});

test('renders SIH validation status, commands, and latest manifest evidence', async () => {
  apiFetch.mockResolvedValueOnce(jsonResponse(statusPayload()));

  render(<ValidationPage />);

  expect(await screen.findByText('Validation')).toBeInTheDocument();
  expect(await screen.findByText('Official PX4 SIH')).toBeInTheDocument();
  expect(screen.getByText('Phase 2 PX4-In-Loop Follower Validation')).toBeInTheDocument();
  expect(screen.getByText('make sitl-sih-dry-run')).toBeInTheDocument();
  expect(screen.getByText('make sitl-sih-probe')).toBeInTheDocument();
  expect(screen.getByText('make sitl-sih-execute-px4')).toBeInTheDocument();
  expect(screen.getAllByText('Requires prepared stack').length).toBeGreaterThan(0);
  expect(screen.getByText('sih-demo-run')).toBeInTheDocument();
  expect(screen.getAllByText('incomplete').length).toBeGreaterThan(0);
  expect(screen.getByText('probes/pixeagle_status.json')).toBeInTheDocument();
  expect(screen.getByText(/mavlink_anywhere_required_outputs/)).toBeInTheDocument();
  expect(screen.getByText('PixEagle SIH/SITL training metadata only.')).toBeInTheDocument();
  expect(apiFetch).toHaveBeenCalledWith(endpoints.sitlValidationStatus);
});

test('renders no-manifest guidance without runtime action buttons', async () => {
  apiFetch.mockResolvedValueOnce(jsonResponse(statusPayload({
    available: false,
    run_id: null,
    result: null,
    missing_or_placeholder_artifacts: [],
    missing_or_placeholder_count: 0,
    semantic_failures: [],
  })));

  render(<ValidationPage />);

  expect(await screen.findByText('No local SIH manifest found.')).toBeInTheDocument();
  expect(screen.getByText(/Run `make sitl-sih-dry-run`/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /start/i })).not.toBeInTheDocument();
});

test('does not fetch validation status without debug scope', async () => {
  mockCanReadValidation = false;

  render(<ValidationPage />);

  expect(screen.getByText('Validation status requires debug access.')).toBeInTheDocument();
  await waitFor(() => expect(apiFetch).not.toHaveBeenCalled());
});

test('refreshes the typed validation status endpoint', async () => {
  apiFetch.mockResolvedValue(jsonResponse(statusPayload()));

  render(<ValidationPage />);

  await screen.findByText('sih-demo-run');
  fireEvent.click(screen.getByRole('button', { name: /refresh/i }));

  await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
});

test('marks prior validation data stale after a failed refresh', async () => {
  apiFetch
    .mockResolvedValueOnce(jsonResponse(statusPayload()))
    .mockResolvedValueOnce(jsonResponse({ detail: 'boom' }, 500));

  render(<ValidationPage />);

  await screen.findByText('sih-demo-run');
  fireEvent.click(screen.getByRole('button', { name: /refresh/i }));

  expect(await screen.findByText(/Validation status request failed/)).toBeInTheDocument();
  expect(screen.getByText(/Showing the last loaded validation data/)).toBeInTheDocument();
  expect(screen.getByText('sih-demo-run')).toBeInTheDocument();
});
