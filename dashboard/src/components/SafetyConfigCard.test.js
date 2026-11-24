import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SafetyConfigCard from './SafetyConfigCard';
import { useSafetyLimits } from '../hooks/useSafetyConfig';

jest.mock('../hooks/useSafetyConfig', () => ({ useSafetyLimits: jest.fn() }));

test('summarizes an absent ceiling explicitly while retaining the floor', () => {
  useSafetyLimits.mockReturnValue({ limits: {
    velocity: {}, rates: {}, altitude: { min: 3, max: null, warning_buffer: 2 },
  }, loading: false, error: null });
  render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <SafetyConfigCard followerName="FW_NAVIGATION_CHASE" />
  </MemoryRouter>);
  expect(screen.getByText('No mission ceiling')).toBeInTheDocument();
  expect(screen.getByText('3 m')).toBeInTheDocument();
});
