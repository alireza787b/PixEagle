import React, { useContext } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { CssBaseline, ThemeProvider as MuiThemeProvider, createTheme } from '@mui/material';
import Layout from './components/Layout';
import TrackerPage from './pages/TrackerPage';
import FollowerPage from './pages/FollowerPage';
import DashboardPage from './pages/DashboardPage';
import LiveFeedPage from './pages/LiveFeedPage';
import SettingsPage from './pages/SettingsPage';
import RecordingsPage from './pages/RecordingsPage';
import ModelsPage from './pages/ModelsPage';
import { ThemeProvider, ThemeContext } from './context/ThemeContext';

// Auto-detect base path for reverse proxy support (e.g., ARK-OS serves at /pixeagle/)
const detectBasePath = () => {
  const path = window.location.pathname;
  const match = path.match(/^(\/pixeagle)/);
  return match ? match[1] : '';
};

const AppContent = () => {
  const { theme } = useContext(ThemeContext);

  const muiTheme = createTheme({
    palette: {
      mode: theme,
    },
  });

  return (
    <MuiThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Router basename={detectBasePath()}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="tracker" element={<TrackerPage />} />
            <Route path="follower" element={<FollowerPage />} />
            <Route path="live-feed" element={<LiveFeedPage />} />
            <Route path="recordings" element={<RecordingsPage />} />
            <Route path="models" element={<ModelsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </Router>
    </MuiThemeProvider>
  );
};

const App = () => (
  <ThemeProvider>
    <AppContent />
  </ThemeProvider>
);

export default App;
