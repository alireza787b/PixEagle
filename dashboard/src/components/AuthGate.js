import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import LoginIcon from '@mui/icons-material/Login';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useAuthSession } from '../context/AuthSessionContext';

const AuthGate = ({ children }) => {
  const {
    authMode,
    loading,
    loginPending,
    error,
    requiresLogin,
    refreshSession,
    login,
    clearError,
  } = useAuthSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLocalError(null);
    clearError();

    try {
      await login({ username, password });
      setPassword('');
    } catch (loginError) {
      setLocalError(loginError.message || 'Login failed.');
    }
  };

  if (loading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <Stack alignItems="center" spacing={2}>
          <CircularProgress />
          <Typography variant="body2" color="text.secondary">
            Checking PixEagle session
          </Typography>
        </Stack>
      </Box>
    );
  }

  if (authMode === 'machine_bearer') {
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 2 }}>
        <Paper sx={{ width: '100%', maxWidth: 480, p: 3, borderRadius: 1 }} variant="outlined">
          <Stack spacing={2}>
            <Typography variant="h6">Dashboard access unavailable</Typography>
            <Alert severity="warning">
              The backend is using machine bearer-token mode. Use local compatibility
              for same-host development or browser-session mode for the dashboard.
            </Alert>
            <Button startIcon={<RefreshIcon />} onClick={() => refreshSession().catch(() => {})}>
              Retry
            </Button>
          </Stack>
        </Paper>
      </Box>
    );
  }

  if (!requiresLogin) {
    return children;
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 2 }}>
      <Paper sx={{ width: '100%', maxWidth: 420, p: 3, borderRadius: 1 }} variant="outlined">
        <Stack component="form" spacing={2} onSubmit={handleSubmit}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>
              PixEagle
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Operator sign in
            </Typography>
          </Box>

          {(localError || error) && (
            <Alert severity="error">
              {localError || error}
            </Alert>
          )}

          <TextField
            label="Username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoFocus
            required
            fullWidth
          />
          <TextField
            label="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
            required
            fullWidth
          />

          <Button
            type="submit"
            variant="contained"
            startIcon={<LoginIcon />}
            disabled={loginPending}
            fullWidth
          >
            {loginPending ? 'Signing in...' : 'Sign In'}
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
};

export default AuthGate;
