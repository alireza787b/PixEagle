import { fireEvent, render, screen } from '@testing-library/react';
import GenericObjectRenderer from './GenericObjectRenderer';

test('generic object editing preserves nullable numeric values and sibling fields', () => {
  const change = jest.fn();
  const schema = { type: 'object', properties: {
    MAX_ALTITUDE: { type: 'float', nullable: true, null_label: 'No mission ceiling', default: 120 },
    MIN_ALTITUDE: { type: 'float' },
  } };
  render(<GenericObjectRenderer value={{ MIN_ALTITUDE: 3, MAX_ALTITUDE: null }} schema={schema} onChange={change} />);
  expect(screen.getByText('No mission ceiling')).toBeInTheDocument();
  expect(screen.queryByDisplayValue('120')).not.toBeInTheDocument();
  expect(screen.queryByDisplayValue('0')).not.toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Set value' }));
  expect(change).toHaveBeenCalledWith({ MIN_ALTITUDE: 3, MAX_ALTITUDE: 120 });
});
