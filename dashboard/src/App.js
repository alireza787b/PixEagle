// src/App.js

import React, { useContext } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { CssBaseline, ThemeProvider as MuiThemeProvider, createTheme } from '@mui/material';
import Layout from './components/Layout';
import TrackerPage from './pages/TrackerPage';
import FollowerPage from './pages/FollowerPage';
import DashboardPage from './pages/DashboardPage';
import LiveFeedPage from './pages/LiveFeedPage';
import { ThemeProvider, ThemeContext } from './context/ThemeContext';

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
      <Router>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="tracker" element={<TrackerPage />} />
            <Route path="follower" element={<FollowerPage />} />
            <Route path="live-feed" element={<LiveFeedPage />} />
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
