import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import FollowerConfigEditor from './FollowerConfigEditor';

const mockUseResponsive = jest.fn(() => ({ isMobile: false, isTablet: false }));

jest.mock('../../hooks/useResponsive', () => ({
  useResponsive: () => mockUseResponsive(),
}));

beforeEach(() => {
  mockUseResponsive.mockReturnValue({ isMobile: false, isTablet: false });
});

test('renders guidance choices from the backend General schema without direct mode', async () => {
  render(
    <FollowerConfigEditor
      type="General"
      value={{ LATERAL_GUIDANCE_MODE: 'coordinated_turn' }}
      onChange={jest.fn()}
      schema={{
        type: 'object',
        properties: {
          LATERAL_GUIDANCE_MODE: {
            type: 'string',
            default: 'coordinated_turn',
            options: [
              { value: 'coordinated_turn', label: 'Coordinated turn' },
              { value: 'sideslip', label: 'Sideslip' },
            ],
          },
        },
      }}
    />
  );

  fireEvent.mouseDown(screen.getByRole('combobox'));

  expect(await screen.findByRole('option', { name: 'Coordinated turn' })).toBeInTheDocument();
  expect(screen.getByRole('option', { name: 'Sideslip' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: /direct/i })).not.toBeInTheDocument();
});

test('renders cards instead of tables on mobile', () => {
  mockUseResponsive.mockReturnValue({ isMobile: true, isTablet: false });
  render(
    <FollowerConfigEditor
      type="General"
      value={{ CONTROL_UPDATE_RATE: 20 }}
      onChange={jest.fn()}
      schema={{
        type: 'object',
        properties: {
          CONTROL_UPDATE_RATE: { type: 'float', default: 20, min: 1, max: 50 },
        },
      }}
    />
  );

  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.getByRole('spinbutton')).toBeInTheDocument();
});

test('shows an undeclared current follower as a read-only migration case', async () => {
  const onChange = jest.fn();
  const referenceSchema = {
    type: 'object',
    properties: {
      CONTROL_UPDATE_RATE: { type: 'float', default: 20, min: 1, max: 50 },
    },
  };
  render(
    <FollowerConfigEditor
      type="FollowerOverrides"
      value={{ LEGACY_PROFILE: { CONTROL_UPDATE_RATE: 15 } }}
      generalDefaults={{ CONTROL_UPDATE_RATE: 20 }}
      onChange={onChange}
      referenceSchema={referenceSchema}
      schema={{
        type: 'object',
        additional_properties: false,
        properties: {
          DECLARED_PROFILE: {
            type: 'object',
            properties: {
              CONTROL_UPDATE_RATE: referenceSchema.properties.CONTROL_UPDATE_RATE,
            },
          },
        },
      }}
    />
  );

  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name: /Legacy Profile/i }));

  expect(screen.getByText(/read-only migration case/i)).toBeInTheDocument();
  expect(screen.getByDisplayValue('15')).toBeDisabled();
  expect(onChange).not.toHaveBeenCalled();
});
