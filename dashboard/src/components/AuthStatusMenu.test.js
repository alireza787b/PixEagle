import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AuthStatusMenu from './AuthStatusMenu';

let mockAuthSession;

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => mockAuthSession,
}));

jest.mock('./AccountManagementDialog', () => ({ open, onClose }) => (
  open ? (
    <div role="dialog" aria-label="Account test dialog">
      <button type="button" onClick={onClose}>Close test dialog</button>
    </div>
  ) : null
));

beforeEach(() => {
  mockAuthSession = {
    authenticated: true,
    principal: { subject: 'operator', role: 'operator', scopes: [] },
    usesBrowserSession: true,
    logout: jest.fn(),
    logoutPending: false,
  };
});

test('opens account management from the existing account chip', () => {
  render(<AuthStatusMenu />);

  fireEvent.click(screen.getByRole('button', { name: 'Manage account for operator' }));
  expect(screen.getByRole('dialog', { name: 'Account test dialog' })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Close test dialog' }));
  expect(screen.queryByRole('dialog', { name: 'Account test dialog' })).not.toBeInTheDocument();
});

test('keeps sign out as a separate explicit action', () => {
  render(<AuthStatusMenu />);

  fireEvent.click(screen.getByRole('button', { name: 'sign out' }));
  expect(mockAuthSession.logout).toHaveBeenCalledTimes(1);
});
