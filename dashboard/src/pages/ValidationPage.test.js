import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ValidationPage from './ValidationPage';
import { apiFetch, apiFetchJson } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

let mockCanReadValidation = true;
let mockCanManageValidation = true;

jest.mock('../services/apiClient', () => ({
  apiFetch: jest.fn(),
  apiFetchJson: jest.fn(),
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: (scope) => (
      (scope === 'debug:read' && mockCanReadValidation)
      || (scope === 'system:admin' && mockCanManageValidation)
    ),
  }),
}));

const jsonResponse = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
});

const statusPayload = (latestRun = {}) => ({
  schema_version: 3,
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
  managed_lifecycle: {
    feature_enabled: true,
    readiness: 'ready',
    docker_cli_available: true,
    docker_daemon_accessible: true,
    docker_server_version: '27.5.1',
    image_available: true,
    container_name: 'pixeagle-managed-px4-sih',
    container_state: 'absent',
    container_id: null,
    ownership_verified: false,
    start_available: true,
    stop_available: false,
    start_path: '/api/v1/actions/managed-sih-start',
    stop_path: '/api/v1/actions/managed-sih-stop',
    px4_connected: false,
    system_address: 'udp://127.0.0.1:14540',
    control_state_available: true,
    control_active: false,
    routing_managed_by_dashboard: false,
    start_requires_no_real_aircraft_confirmation: true,
    stop_requires_no_real_aircraft_confirmation: false,
    reasons: [],
    warnings: [],
  },
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
  mockCanManageValidation = true;
  apiFetch.mockReset();
  apiFetchJson.mockReset();
});

test('renders SIH validation status, commands, and latest manifest evidence', async () => {
  apiFetch.mockResolvedValueOnce(jsonResponse(statusPayload()));

  render(<ValidationPage />);

  expect(await screen.findByText('PX4 Validation')).toBeInTheDocument();
  expect(await screen.findByText('Managed SIH')).toBeInTheDocument();
  expect(screen.getByText('make sitl-sih-dry-run')).toBeInTheDocument();
  expect(screen.getByText('make sitl-sih-probe')).toBeInTheDocument();
  expect(screen.getByText('make sitl-sih-execute-px4')).toBeInTheDocument();
  expect(screen.getByText(/^sih-demo-run -/)).toBeInTheDocument();
  expect(screen.getAllByText('incomplete').length).toBeGreaterThan(0);
  expect(screen.getByText('probes/pixeagle_status.json')).toBeInTheDocument();
  expect(screen.getByText(/mavlink_anywhere_required_outputs/)).toBeInTheDocument();
  expect(apiFetch).toHaveBeenCalledWith(endpoints.sitlValidationStatus);
});

test('renders no-manifest guidance with lifecycle actions derived from readiness', async () => {
  apiFetch.mockResolvedValueOnce(jsonResponse(statusPayload({
    available: false,
    run_id: null,
    result: null,
    missing_or_placeholder_artifacts: [],
    missing_or_placeholder_count: 0,
    semantic_failures: [],
  })));

  render(<ValidationPage />);

  expect(await screen.findByText(/No local validation manifest/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Start SIH' })).toBeEnabled();
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

  await screen.findByText(/^sih-demo-run -/);
  fireEvent.click(screen.getByRole('button', { name: /refresh/i }));

  await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
});

test('marks prior validation data stale after a failed refresh', async () => {
  apiFetch
    .mockResolvedValueOnce(jsonResponse(statusPayload()))
    .mockResolvedValueOnce(jsonResponse({ detail: 'boom' }, 500));

  render(<ValidationPage />);

  await screen.findByText(/^sih-demo-run -/);
  fireEvent.click(screen.getByRole('button', { name: /refresh/i }));

  expect(await screen.findByText(/Validation status request failed/)).toBeInTheDocument();
  expect(screen.getByText(/Showing stale validation status/)).toBeInTheDocument();
  expect(screen.getByText(/^sih-demo-run -/)).toBeInTheDocument();
});

test('starts only after the explicit no-real-aircraft confirmation', async () => {
  apiFetch.mockResolvedValue(jsonResponse(statusPayload()));
  apiFetchJson.mockResolvedValue({
    status: 'success',
    accepted: true,
  });

  render(<ValidationPage />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start SIH' }));
  expect(screen.getByText(/no real aircraft, HIL rig/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

  await waitFor(() => expect(apiFetchJson).toHaveBeenCalledTimes(1));
  const [url, request] = apiFetchJson.mock.calls[0];
  expect(url).toBe(endpoints.managedSihStartAction);
  expect(JSON.parse(request.body)).toEqual(expect.objectContaining({
    confirm: true,
    no_real_aircraft_confirmed: true,
    idempotency_key: expect.stringMatching(/^dashboard-managed-sih-start-/),
  }));
});

test('stops an owned simulator without the start-only hardware acknowledgement', async () => {
  const payload = statusPayload();
  payload.managed_lifecycle = {
    ...payload.managed_lifecycle,
    readiness: 'running',
    container_state: 'running',
    ownership_verified: true,
    start_available: false,
    stop_available: true,
  };
  apiFetch.mockResolvedValue(jsonResponse(payload));
  apiFetchJson.mockResolvedValue({ status: 'success', accepted: true });

  render(<ValidationPage />);

  fireEvent.click(await screen.findByRole('button', { name: 'Stop SIH' }));
  expect(screen.queryByText(/no real aircraft, HIL rig/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

  await waitFor(() => expect(apiFetchJson).toHaveBeenCalledTimes(1));
  const [url, request] = apiFetchJson.mock.calls[0];
  const body = JSON.parse(request.body);
  expect(url).toBe(endpoints.managedSihStopAction);
  expect(body.confirm).toBe(true);
  expect(body.idempotency_key).toMatch(/^dashboard-managed-sih-stop-/);
  expect(body).not.toHaveProperty('no_real_aircraft_confirmed');
});

test('keeps lifecycle mutations disabled without system administrator scope', async () => {
  mockCanManageValidation = false;
  apiFetch.mockResolvedValueOnce(jsonResponse(statusPayload()));

  render(<ValidationPage />);

  expect(await screen.findByRole('button', { name: 'Start SIH' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Stop SIH' })).toBeDisabled();
});

test('shows the exact blocker when a running SIH container cannot be stopped', async () => {
  const payload = statusPayload();
  payload.managed_lifecycle = {
    ...payload.managed_lifecycle,
    readiness: 'running',
    container_state: 'running',
    start_available: false,
    stop_available: false,
    control_state_available: false,
    reasons: ['control_activity_state_unavailable'],
  };
  apiFetch.mockResolvedValueOnce(jsonResponse(payload));

  render(<ValidationPage />);

  expect(await screen.findByText('Unknown')).toBeInTheDocument();
  expect(screen.getByText(
    'PixEagle could not verify following and Offboard state.'
  )).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Stop SIH' })).toBeDisabled();
});
