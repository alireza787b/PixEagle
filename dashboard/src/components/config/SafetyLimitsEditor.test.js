import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import SafetyLimitsEditor from './SafetyLimitsEditor';

const mockUseResponsive = jest.fn(() => ({ isMobile: false, isTablet: false }));

jest.mock('../../hooks/useResponsive', () => ({
  useResponsive: () => mockUseResponsive(),
}));

beforeEach(() => {
  mockUseResponsive.mockReturnValue({ isMobile: false, isTablet: false });
});

test('applies exact numeric constraints from the backend GlobalLimits schema', () => {
  render(
    <SafetyLimitsEditor
      type="GlobalLimits"
      value={{ MAX_VELOCITY_LATERAL: 1.5 }}
      onChange={jest.fn()}
      schema={{
        type: 'object',
        required: ['MAX_VELOCITY_LATERAL'],
        additional_properties: false,
        properties: {
          MAX_VELOCITY_LATERAL: {
            type: 'float',
            default: 1.5,
            min: 0.25,
            max: 7.75,
            step: 0.25,
            unit: 'm/s',
            description: 'Backend-owned lateral velocity limit',
          },
        },
      }}
    />
  );

  expect(screen.getByRole('spinbutton')).toHaveAttribute('min', '0.25');
  expect(screen.getByRole('spinbutton')).toHaveAttribute('max', '7.75');
  expect(screen.getByRole('spinbutton')).toHaveAttribute('step', '0.25');
  expect(screen.queryByRole('button', { name: /Add Property/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Remove this override/i })).not.toBeInTheDocument();
});

test('renders touch-friendly cards on tablet', () => {
  mockUseResponsive.mockReturnValue({ isMobile: false, isTablet: true });
  render(
    <SafetyLimitsEditor
      type="GlobalLimits"
      value={{ MAX_VELOCITY: 2 }}
      onChange={jest.fn()}
      schema={{
        type: 'object',
        required: ['MAX_VELOCITY'],
        properties: {
          MAX_VELOCITY: { type: 'float', default: 2, min: 0, max: 5 },
        },
      }}
    />
  );

  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.getByRole('spinbutton')).toBeInTheDocument();
});

test('edits an explicit absent global ceiling without substituting the default', () => {
  const change = jest.fn();
  const schema = { type: 'object', required: ['MAX_ALTITUDE'], properties: {
    MAX_ALTITUDE: { type: 'float', nullable: true, null_label: 'No mission ceiling', default: 120 },
  } };
  render(<SafetyLimitsEditor type="GlobalLimits" value={{ MAX_ALTITUDE: null }} onChange={change} schema={schema} />);
  expect(screen.getByText('No mission ceiling')).toBeInTheDocument();
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Set value' }));
  expect(change).toHaveBeenCalledWith({ MAX_ALTITUDE: 120 });
});

test('keeps undeclared safety followers visible but read-only', async () => {
  const globalSchema = {
    type: 'object',
    properties: {
      MAX_VELOCITY: { type: 'float', default: 2, min: 0, max: 5 },
    },
  };
  render(
    <SafetyLimitsEditor
      type="FollowerOverrides"
      value={{ LEGACY_PROFILE: { MAX_VELOCITY: 1 } }}
      globalLimits={{ MAX_VELOCITY: 2 }}
      onChange={jest.fn()}
      referenceSchema={globalSchema}
      schema={{
        type: 'object',
        additional_properties: false,
        properties: {
          DECLARED_PROFILE: {
            type: 'object',
            properties: globalSchema.properties,
          },
        },
      }}
    />
  );

  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name: /Legacy Profile/i }));

  expect(screen.getByText(/read-only migration case/i)).toBeInTheDocument();
  expect(screen.getByDisplayValue('1')).toBeDisabled();
});
