import React, { useContext, useEffect } from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { CssBaseline, ThemeProvider as MuiThemeProvider, createTheme } from '@mui/material';
import Layout from './components/Layout';
import AuthGate from './components/AuthGate';
import TrackerPage from './pages/TrackerPage';
import FollowerPage from './pages/FollowerPage';
import DashboardPage from './pages/DashboardPage';
import LiveFeedPage from './pages/LiveFeedPage';
import SettingsPage from './pages/SettingsPage';
import RecordingsPage from './pages/RecordingsPage';
import ModelsPage from './pages/ModelsPage';
import LogsPage from './pages/LogsPage';
import ValidationPage from './pages/ValidationPage';
import { ThemeProvider, ThemeContext } from './context/ThemeContext';
import { AuthSessionProvider } from './context/AuthSessionContext';
import { PendingRestartProvider } from './context/PendingRestartContext';
import { installFrontendErrorReporter } from './services/frontendErrorReporter';

// Auto-detect base path for reverse proxy support (e.g., ARK-OS serves at /pixeagle/)
const detectBasePath = () => {
  const path = window.location.pathname;
  const match = path.match(/^(\/pixeagle)/);
  return match ? match[1] : '';
};

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'tracker', element: <TrackerPage /> },
      { path: 'follower', element: <FollowerPage /> },
      { path: 'live-feed', element: <LiveFeedPage /> },
      { path: 'recordings', element: <RecordingsPage /> },
      { path: 'models', element: <ModelsPage /> },
      { path: 'logs', element: <LogsPage /> },
      { path: 'validation', element: <ValidationPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
], { basename: detectBasePath(), future: { v7_relativeSplatPath: true } });

const AppContent = () => {
  const { theme } = useContext(ThemeContext);

  useEffect(() => installFrontendErrorReporter(), []);

  const muiTheme = createTheme({
    palette: {
      mode: theme,
    },
  });

  return (
    <MuiThemeProvider theme={muiTheme}>
      <CssBaseline />
      <AuthGate>
        <PendingRestartProvider>
          <RouterProvider router={router} future={{ v7_startTransition: true }} />
        </PendingRestartProvider>
      </AuthGate>
    </MuiThemeProvider>
  );
};

const App = () => (
  <ThemeProvider>
    <AuthSessionProvider>
      <AppContent />
    </AuthSessionProvider>
  </ThemeProvider>
);

export default App;
