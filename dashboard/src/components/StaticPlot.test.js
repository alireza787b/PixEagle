import React from 'react';
import { render, screen } from '@testing-library/react';
import StaticPlot from './StaticPlot';

const mockLine = jest.fn(() => <div data-testid="line-chart" />);

jest.mock('react-chartjs-2', () => ({
  Line: (props) => mockLine(props),
}));

beforeEach(() => {
  mockLine.mockClear();
});

const samples = (values, buildSample = (value) => ({ vel_x: value })) => values.map(
  (value, index) => ({
    timestamp: `2026-01-01T00:00:0${index}.000Z`,
    ...buildSample(value),
  })
);

test('uses gaps for missing and nonfinite follower samples while preserving zero', () => {
  render(
    <StaticPlot
      title="Velocity X"
      data={samples([1, undefined, null, Number.NaN, Number.POSITIVE_INFINITY, 0])}
      dataKey="vel_x"
    />
  );

  const { data } = mockLine.mock.calls[0][0];
  expect(data.datasets[0].data).toEqual([1, null, null, null, null, 0]);
  expect(data.datasets[0].spanGaps).toBe(false);
  expect(screen.getByText('Current vel_x: 0')).toBeInTheDocument();
});

test('renders the latest invalid plot value as unavailable', () => {
  render(
    <StaticPlot
      title="Velocity X"
      data={samples([0, Number.NaN])}
      dataKey="vel_x"
    />
  );

  expect(mockLine.mock.calls[0][0].data.datasets[0].data).toEqual([0, null]);
  expect(screen.getByText('Current vel_x: --')).toBeInTheDocument();
});

test('does not fabricate tracker or schema-field values', () => {
  const { rerender } = render(
    <StaticPlot
      title="Center X"
      data={samples([[0, 1], [Number.NaN, 2], null], (center) => ({ center }))}
      dataKey="center.0"
    />
  );

  expect(mockLine.mock.calls[0][0].data.datasets[0].data).toEqual([0, null, null]);

  rerender(
    <StaticPlot
      title="Position"
      data={samples([[0, 1], [], [Number.POSITIVE_INFINITY]], (position) => ({
        fields: { position },
      }))}
      dataKey="position"
    />
  );

  const lastCall = mockLine.mock.calls[mockLine.mock.calls.length - 1][0];
  expect(lastCall.data.datasets[0].data).toEqual([0, null, null]);
});

test('waits for data when every plot sample is unavailable', () => {
  render(
    <StaticPlot
      title="Velocity X"
      data={samples([undefined, Number.NaN])}
      dataKey="vel_x"
    />
  );

  expect(screen.getByText('Waiting for data...')).toBeInTheDocument();
  expect(mockLine).not.toHaveBeenCalled();
});
