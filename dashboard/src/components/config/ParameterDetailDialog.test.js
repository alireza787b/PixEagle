import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import ParameterDetailDialog from './ParameterDetailDialog';

jest.mock('../../hooks/useResponsive', () => ({
  useResponsive: () => ({
    isMobile: false,
    buttonSize: 'small',
    iconButtonSize: 'small',
  }),
}));

const renderDialog = (paramSchema) => render(
  <ParameterDetailDialog
    open
    onClose={jest.fn()}
    param="FOLLOWER_MODE"
    paramSchema={paramSchema}
    currentValue="mc_velocity_position"
    defaultValue="mc_velocity_position"
    onSave={jest.fn()}
  />
);

test('closed catalog options do not expose a custom-value bypass', async () => {
  renderDialog({
    type: 'string',
    options: [
      { value: 'mc_velocity_position', label: 'MC Velocity Position' },
      { value: 'mc_velocity_chase', label: 'MC Velocity Chase' },
    ],
  });

  fireEvent.mouseDown(screen.getByRole('combobox'));

  expect(await screen.findByRole('option', { name: 'MC Velocity Chase' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: /Enter custom value/i })).not.toBeInTheDocument();
});

test('closed catalogs identify a retired saved value without accepting it as custom', async () => {
  render(
    <ParameterDetailDialog
      open
      onClose={jest.fn()}
      param="FOLLOWER_MODE"
      paramSchema={{
        type: 'string',
        options: [
          { value: 'mc_velocity_position', label: 'MC Velocity Position' },
        ],
      }}
      currentValue="retired_follower"
      defaultValue="mc_velocity_position"
      onSave={jest.fn()}
    />
  );

  expect(screen.getByRole('combobox')).toHaveTextContent('retired_follower (unavailable)');
  fireEvent.mouseDown(screen.getByRole('combobox'));
  expect(
    await screen.findByRole('option', {
      name: /retired_follower Saved value is not in the supported catalog/i,
    })
  ).toBeInTheDocument();
});

test('custom values remain available only for schemas that opt in', async () => {
  renderDialog({
    type: 'string',
    allow_custom_values: true,
    options: [
      { value: 'mc_velocity_position', label: 'MC Velocity Position' },
    ],
  });

  fireEvent.mouseDown(screen.getByRole('combobox'));

  expect(await screen.findByRole('option', { name: /Enter custom value/i })).toBeInTheDocument();
});
