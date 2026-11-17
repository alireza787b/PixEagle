import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { AddPropertyDialog, PropertyCard, PropertyValueEditor } from './PropertyEditorShared';

test('renders declared strings as text instead of numeric inputs', () => {
  const onChange = jest.fn();
  render(
    <PropertyCard
      propertyName="LABEL"
      value="camera"
      onChange={onChange}
      onRemove={jest.fn()}
      getPropertyMeta={() => ({ type: 'string', schemaType: 'string', editable: true })}
    />
  );

  const input = screen.getByDisplayValue('camera');
  expect(input).toHaveAttribute('type', 'text');
  fireEvent.change(input, { target: { value: 'front-camera' } });
  expect(onChange).toHaveBeenCalledWith('LABEL', 'front-camera');
});

test('renders unsupported structures read-only instead of coercing them to numbers', () => {
  const onChange = jest.fn();
  render(
    <PropertyCard
      propertyName="PIPELINE"
      value={{ stage: 'decode' }}
      onChange={onChange}
      onRemove={jest.fn()}
      getPropertyMeta={() => ({
        type: 'object',
        schemaType: 'object',
        editable: false,
        readOnlyReason: 'Missing nested properties',
      })}
    />
  );

  expect(screen.getByDisplayValue(/"stage": "decode"/)).toBeDisabled();
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

test('locks a closed enum when its current value is outside the contract', () => {
  render(
    <PropertyCard
      propertyName="MODE"
      value="legacy"
      onChange={jest.fn()}
      onRemove={jest.fn()}
      getPropertyMeta={() => ({
        type: 'enum',
        schemaType: 'string',
        editable: true,
        allowCustomValues: false,
        options: [{ value: 'safe', label: 'Safe' }],
      })}
    />
  );

  expect(screen.getByRole('combobox')).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByText('Needs migration')).toBeInTheDocument();
});

const ceilingMeta = {
  type: 'number', schemaType: 'float', editable: true, nullable: true,
  nullLabel: 'No mission ceiling', default: 120, min: 1, max: 500,
};

test('keeps an absent ceiling explicit until the operator chooses a finite value', () => {
  const change = jest.fn();
  const { rerender } = render(<PropertyValueEditor propMeta={ceilingMeta} value={null} onChange={change} />);
  expect(screen.getByText('No mission ceiling')).toBeInTheDocument();
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Set value' }));
  expect(change).toHaveBeenLastCalledWith(120);
  rerender(<PropertyValueEditor propMeta={ceilingMeta} value={120} onChange={change} />);
  fireEvent.click(screen.getByRole('button', { name: 'No mission ceiling' }));
  expect(change).toHaveBeenLastCalledWith(null);
});

test('disables edits to an absent ceiling when configuration is read-only', () => {
  render(<PropertyValueEditor propMeta={ceilingMeta} value={null} onChange={jest.fn()} disabled />);
  expect(screen.getByRole('button', { name: 'Set value' })).toBeDisabled();
});

test('requires an explicit finite follower cap when the global ceiling is absent', async () => {
  const add = jest.fn();
  const meta = { name: 'MAX_ALTITUDE', type: 'number', schemaType: 'float', editable: true,
    category: 'altitude', min: .000001, max: 500 };
  render(<AddPropertyDialog open onClose={jest.fn()} onAdd={add}
    referenceDefaults={{ MAX_ALTITUDE: null }} getPropertyMeta={() => meta}
    getAddableProperties={() => [meta]} />);
  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name: /MAX_ALTITUDE/i }));
  expect(screen.getByRole('spinbutton')).toHaveValue(null);
  expect(screen.getByRole('button', { name: 'Add Property' })).toBeDisabled();
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '75' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add Property' }));
  expect(add).toHaveBeenCalledWith('MAX_ALTITUDE', 75, null);
});
