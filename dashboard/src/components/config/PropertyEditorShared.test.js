import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { PropertyCard } from './PropertyEditorShared';

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
