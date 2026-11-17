import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import yaml from 'js-yaml';
import axios from '../../services/apiClient';
import { endpoints } from '../../services/apiEndpoints';
import ExportDialog from './ExportDialog';
import ImportDialog from './ImportDialog';

jest.mock('../../services/apiClient', () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock('../../hooks/useConfig', () => ({ useConfigDiff: () => ({ diff: [], loading: false }) }));
jest.mock('./DiffViewer', () => () => null);

test('exports YAML null and imports it without converting it to an omitted value or zero', async () => {
  const config = { Safety: { GlobalLimits: { MIN_ALTITUDE: 3, MAX_ALTITUDE: null } } };
  axios.get.mockResolvedValue({ data: { success: true, config } });
  let exportedBlob;
  window.URL.createObjectURL = jest.fn((blob) => { exportedBlob = blob; return 'blob:test'; });
  window.URL.revokeObjectURL = jest.fn();
  const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const close = jest.fn();
  const { unmount } = render(<ExportDialog open onClose={close} />);
  fireEvent.click(screen.getByRole('button', { name: 'Export' }));
  await waitFor(() => expect(close).toHaveBeenCalledWith(true));
  const text = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsText(exportedBlob);
  });
  expect(yaml.load(text)).toEqual(config);
  unmount();
  click.mockRestore();

  axios.post.mockResolvedValueOnce({ data: { success: true, differences: [{
    section: 'Safety', parameter: 'GlobalLimits', old_value: { MAX_ALTITUDE: 120 },
    new_value: config.Safety.GlobalLimits,
  }] } }).mockResolvedValueOnce({ data: { success: true, changes_applied: 1 } });
  render(<ImportDialog open onClose={jest.fn()} />);
  const file = new File([text], 'ceiling.yaml', { type: 'application/x-yaml' });
  file.text = async () => text;
  fireEvent.change(screen.getByLabelText('Configuration YAML file'), { target: { files: [file] } });
  fireEvent.click(await screen.findByRole('button', { name: /Import 1 Changes/i }));
  await screen.findByText('Import Successful');
  expect(axios.post).toHaveBeenCalledWith(endpoints.configDiff, { compare_config: config });
  expect(axios.post).toHaveBeenCalledWith(endpoints.configImport, { data: config, merge_mode: 'merge' });
});
