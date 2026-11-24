import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import SectionEditor from './SectionEditor';

const schema = { display_name: 'Test section', parameters: {
  ENABLED: { type: 'boolean', label: 'Enable overlay' },
  HOST: { type: 'string', label: 'Server address', read_only: true },
} };

test('dispatches toggles to the draft and keeps schema read-only controls disabled', () => {
  const onEdit = jest.fn();
  render(<SectionEditor section="Test" schema={schema}
    saved={{ ENABLED: false, HOST: 'localhost' }} draft={{}} onEdit={onEdit} />);
  fireEvent.click(screen.getByRole('checkbox', { name: 'Enable overlay' }));
  expect(onEdit).toHaveBeenCalledWith(['Test', 'ENABLED'], true, undefined);
  expect(screen.getByRole('textbox', { name: 'Server address' })).toBeDisabled();
});
