import { render, screen } from '@testing-library/react';

jest.mock('axios', () => {
  const client = {
    get: jest.fn(() => Promise.resolve({ data: {} })),
    post: jest.fn(() => Promise.resolve({ data: {} })),
    put: jest.fn(() => Promise.resolve({ data: {} })),
    delete: jest.fn(() => Promise.resolve({ data: {} })),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };

  return {
    __esModule: true,
    default: {
      ...client,
      create: jest.fn(() => client),
    },
    ...client,
    create: jest.fn(() => client),
  };
});

jest.mock('./components/NavigationDrawer', () => () => <nav>Navigation</nav>);
jest.mock('./components/Footer', () => () => <footer>Footer</footer>);
jest.mock('./components/AuthGate', () => ({ children }) => <>{children}</>);
jest.mock('./components/AuthStatusMenu', () => () => <span data-testid="auth-status">Auth status</span>);
jest.mock('./context/AuthSessionContext', () => ({
  AuthSessionProvider: ({ children }) => <>{children}</>,
  useAuthSession: () => ({
    hasScope: () => true,
    hasAnyScope: () => true,
    usesBrowserSession: false,
    authenticated: false,
  }),
}));
jest.mock('./components/BackendStatusIndicator', () => () => (
  <span data-testid="backend-status">Backend status</span>
));
jest.mock('./pages/TrackerPage', () => () => <div>Tracker Page</div>);
jest.mock('./pages/FollowerPage', () => () => <div>Follower Page</div>);
jest.mock('./pages/DashboardPage', () => () => <div>Dashboard Page</div>);
jest.mock('./pages/LiveFeedPage', () => () => <div>Live Feed Page</div>);
jest.mock('./pages/SettingsPage', () => () => <div>Settings Page</div>);
jest.mock('./pages/RecordingsPage', () => () => <div>Recordings Page</div>);
jest.mock('./pages/ModelsPage', () => () => <div>Models Page</div>);
jest.mock('./pages/LogsPage', () => () => <div>Logs Page</div>);
jest.mock('./pages/ValidationPage', () => () => <div>Validation Page</div>);

const App = require('./App').default;

test('renders the PixEagle dashboard shell', async () => {
  render(<App />);

  expect(await screen.findByText(/PixEagle/i)).toBeInTheDocument();
  expect(await screen.findByText(/Dashboard Page/i)).toBeInTheDocument();
});
