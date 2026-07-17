import { render, screen } from '@testing-library/react';
import SensorsIcon from '@mui/icons-material/Sensors';
import OperatorMetricStrip from './OperatorMetricStrip';

test('renders compact operator metrics', () => {
  render(
    <OperatorMetricStrip
      items={[
        { icon: <SensorsIcon />, label: 'Runtime', value: 'Active', detail: 'CSRT' },
        { icon: <SensorsIcon />, label: 'Age', value: '<1 s', detail: 'Fresh' },
      ]}
    />
  );

  expect(screen.getByText('Runtime')).toBeInTheDocument();
  expect(screen.getByText('<1 s')).toBeInTheDocument();
});
