import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import yaml from 'js-yaml';
import axios from '../../services/apiClient';
import ExportDialog from './ExportDialog';
import { readConfigYaml } from '../../utils/configImport';

jest.mock('../../services/apiClient', () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock('../../hooks/useConfig', () => ({ useConfigDiff: () => ({ diff: [], loading: false }) }));

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

  const file = new File([text], 'ceiling.yaml', { type: 'application/x-yaml' });
  file.text = async () => text;
  expect(await readConfigYaml(file)).toEqual(config);
});
