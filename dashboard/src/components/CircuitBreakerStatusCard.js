// dashboard/src/components/CircuitBreakerStatusCard.js
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Alert,
  Skeleton,
  Switch,
  FormControlLabel,
  Collapse,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import {
  Security,
  Warning,
  Info,
  CheckCircle,
  Block,
  ExpandMore,
  ExpandLess
} from '@mui/icons-material';
import { endpoints } from '../services/apiEndpoints';
import axios from '../services/apiClient';
import { buildActionRequest } from '../services/actionRequests';

const NO_CACHE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

const buildNoCacheConfig = () => ({
  headers: NO_CACHE_HEADERS,
  params: { _t: Date.now() },
});

const errorMessage = (error) => (
  error?.response?.data?.detail?.message
  || error?.response?.data?.detail
  || error?.message
  || 'Circuit-breaker request failed'
);

const requireSuccessfulAction = (response) => {
  if (response?.data?.status !== 'success') {
    throw new Error(response?.data?.error || 'Circuit-breaker state was not confirmed');
  }
};

const CircuitBreakerStatusCard = React.memo(() => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);
  const [statistics, setStatistics] = useState(null);
  const [toggling, setToggling] = useState(false);
  const [showStatistics, setShowStatistics] = useState(false);
  const [safetyBypass, setSafetyBypass] = useState(false);
  const [togglingBypass, setTogglingBypass] = useState(false);
  const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
  const statusRequestRef = useRef(0);
  const statsRequestRef = useRef(0);

  const fetchStatus = useCallback(async ({ suppressError = false } = {}) => {
    const requestId = ++statusRequestRef.current;
    try {
      const response = await axios.get(endpoints.circuitBreakerStatus, buildNoCacheConfig());
      if (requestId !== statusRequestRef.current) {
        return null;
      }

      setStatus(response.data);
      setSafetyBypass(response.data.safety_bypass || false);
      setError(null);
      return response.data;
    } catch (err) {
      if (!suppressError) {
        setError(errorMessage(err));
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchStatistics = useCallback(async ({ suppressError = false } = {}) => {
    const requestId = ++statsRequestRef.current;
    try {
      const response = await axios.get(endpoints.circuitBreakerStats, buildNoCacheConfig());
      if (requestId !== statsRequestRef.current) {
        return null;
      }

      setStatistics(response.data);
      return response.data;
    } catch (err) {
      if (!suppressError) {
        setError(errorMessage(err));
      }
      return null;
    }
  }, []);

  const applyCircuitBreakerState = async (enabled) => {
    if (toggling) return;

    setToggling(true);
    setError(null);
    try {
      const response = await axios.post(
        endpoints.circuitBreakerSetAction,
        {
          ...buildActionRequest(enabled ? 'enable_circuit_breaker' : 'disable_circuit_breaker'),
          enabled,
        },
        { headers: NO_CACHE_HEADERS },
      );
      requireSuccessfulAction(response);
      await fetchStatus({ suppressError: true });
      await fetchStatistics({ suppressError: true });
    } catch (err) {
      setError(errorMessage(err));
      await fetchStatus({ suppressError: true });
    } finally {
      setToggling(false);
    }
  };

  const handleToggle = (_event, enabled) => {
    if (enabled === isActive || toggling) return;
    if (!enabled) {
      setLiveConfirmOpen(true);
      return;
    }
    applyCircuitBreakerState(true);
  };

  const handleSafetyBypassToggle = async (_event, enabled) => {
    if (togglingBypass) return;

    setTogglingBypass(true);
    setError(null);
    try {
      const response = await axios.post(
        endpoints.circuitBreakerSafetyBypassSetAction,
        {
          ...buildActionRequest(
            enabled ? 'enable_circuit_breaker_safety_bypass' : 'disable_circuit_breaker_safety_bypass',
          ),
          enabled,
        },
        { headers: NO_CACHE_HEADERS },
      );
      requireSuccessfulAction(response);
      await fetchStatus({ suppressError: true });
      await fetchStatistics({ suppressError: true });
    } catch (err) {
      setError(errorMessage(err));
      await fetchStatus({ suppressError: true });
    } finally {
      setTogglingBypass(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    // Only fetch statistics initially if user wants to see them
    if (showStatistics) {
      fetchStatistics();
    }

    // Optimized polling: status every 2 seconds, statistics only if shown and less frequently
    const statusInterval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) {
        return;
      }
      fetchStatus({ suppressError: true });
    }, 2000);

    let statisticsInterval = null;
    if (showStatistics) {
      statisticsInterval = setInterval(() => {
        if (typeof document !== 'undefined' && document.hidden) {
          return;
        }
        fetchStatistics({ suppressError: true });
      }, 5000); // Less frequent for statistics
    }

    const handleVisibilityChange = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        fetchStatus({ suppressError: true });
        if (showStatistics) {
          fetchStatistics({ suppressError: true });
        }
      }
    };

    const handleWindowFocus = () => {
      fetchStatus({ suppressError: true });
      if (showStatistics) {
        fetchStatistics({ suppressError: true });
      }
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', handleWindowFocus);
    }

    return () => {
      clearInterval(statusInterval);
      if (statisticsInterval) clearInterval(statisticsInterval);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleWindowFocus);
      }
    };
  }, [showStatistics, fetchStatus, fetchStatistics]); // Re-run when showStatistics changes

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Security color="action" />
            <Typography variant="h6">Circuit breaker</Typography>
          </Box>
          <Skeleton variant="text" width="80%" height={24} />
          <Skeleton variant="text" width="60%" height={20} sx={{ mt: 1 }} />
        </CardContent>
      </Card>
    );
  }

  if (error && !status) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Warning color="error" />
            <Typography variant="h6">Circuit breaker</Typography>
          </Box>
          <Alert severity="error" size="small">
            {error}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (!status?.available) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Block color="disabled" />
            <Typography variant="h6">Circuit breaker</Typography>
          </Box>
          <Alert severity="warning" size="small">
            Circuit breaker system not available
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const isActive = status.active;
  const stats = statistics?.circuit_breaker || {};

  return (
    <Card>
      <CardContent>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <Security color={isActive ? 'warning' : 'success'} />
          <Typography variant="h6">Circuit breaker</Typography>
          <Chip
            label={isActive ? 'ACTIVE' : 'INACTIVE'}
            color={isActive ? 'warning' : 'success'}
            size="small"
            icon={isActive ? <Block /> : <CheckCircle />}
          />
        </Box>

        {/* Toggle Control */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="body2" color="textSecondary">
            Safety Mode:
          </Typography>
          <FormControlLabel
            control={
              <Switch
                checked={isActive}
                onChange={handleToggle}
                disabled={toggling}
                color="warning"
              />
            }
            label={isActive ? 'Testing' : 'Live'}
            labelPlacement="start"
          />
        </Box>

        {/* Status Info */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {isActive ? (
            <Alert severity="warning" size="small" sx={{ mb: 1 }}>
              <Typography variant="caption">
                Drone commands are blocked for safety testing.
              </Typography>
            </Alert>
          ) : (
            <Alert severity="success" size="small" sx={{ mb: 1 }}>
              <Typography variant="caption">
                Live command dispatch is permitted.
              </Typography>
            </Alert>
          )}

          {/* Safety Bypass Toggle - Only visible when CB is active */}
          {isActive && (
            <Box sx={{ mt: 1, p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="body2" color="textSecondary">
                  Safety Bypass:
                </Typography>
                <FormControlLabel
                  control={
                    <Switch
                      checked={safetyBypass}
                      onChange={handleSafetyBypassToggle}
                      disabled={togglingBypass}
                      color="error"
                      size="small"
                    />
                  }
                  label={safetyBypass ? 'ON' : 'OFF'}
                  labelPlacement="start"
                />
              </Box>
              {safetyBypass && (
                <Alert severity="error" size="small" sx={{ mt: 1 }}>
                  <Typography variant="caption">
                    Altitude and velocity checks are bypassed in circuit-breaker testing.
                  </Typography>
                </Alert>
              )}
              {!safetyBypass && (
                <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.5 }}>
                  Enable to bypass altitude safety for ground testing
                </Typography>
              )}
            </Box>
          )}

          {/* Statistics Toggle Button */}
          <Box sx={{ mt: 1, display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small"
              onClick={() => {
                setShowStatistics(!showStatistics);
                if (!showStatistics && !statistics) {
                  fetchStatistics(); // Fetch statistics when first opened
                }
              }}
              startIcon={showStatistics ? <ExpandLess /> : <ExpandMore />}
              sx={{ textTransform: 'none', fontSize: '0.75rem' }}
            >
              {showStatistics ? 'Hide' : 'Show'} Statistics
            </Button>
          </Box>

          {/* Collapsible Statistics */}
          <Collapse in={showStatistics}>
            {statistics?.circuit_breaker && (
              <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
                <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: 'block' }}>
                  Session Statistics:
                </Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Block fontSize="small" color="warning" />
                <Typography variant="caption" sx={{ minWidth: 80 }}>
                  Blocked:
                </Typography>
                <Typography variant="caption" fontFamily="monospace" color="warning.main">
                  {stats.total_commands_blocked || 0}
                </Typography>
              </Box>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <CheckCircle fontSize="small" color="success" />
                <Typography variant="caption" sx={{ minWidth: 80 }}>
                  Allowed:
                </Typography>
                <Typography variant="caption" fontFamily="monospace" color="success.main">
                  {stats.total_commands_allowed || 0}
                </Typography>
              </Box>

              {stats.last_blocked_command && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                  <Info fontSize="small" color="info" />
                  <Typography variant="caption" sx={{ minWidth: 80 }}>
                    Last blocked:
                  </Typography>
                  <Typography variant="caption" fontFamily="monospace" color="info.main">
                    {stats.last_blocked_command}
                  </Typography>
                </Box>
              )}

              {stats.session_start_time && (
                <Typography variant="caption" color="textSecondary" sx={{ mt: 0.5, display: 'block' }}>
                  Session: {new Date(stats.session_start_time * 1000).toLocaleTimeString()}
                </Typography>
              )}
              </Box>
            )}
          </Collapse>
        </Box>

        <Dialog
          open={liveConfirmOpen}
          onClose={() => setLiveConfirmOpen(false)}
          aria-labelledby="circuit-breaker-live-confirm-title"
        >
          <DialogTitle id="circuit-breaker-live-confirm-title">
            Permit live command dispatch?
          </DialogTitle>
          <DialogContent>
            <Alert severity="warning">
              Disabling the circuit breaker permits reviewed follower commands to reach PX4.
              Following must remain stopped while this setting changes.
            </Alert>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setLiveConfirmOpen(false)}>Cancel</Button>
            <Button
              color="warning"
              variant="contained"
              disabled={toggling}
              onClick={() => {
                setLiveConfirmOpen(false);
                applyCircuitBreakerState(false);
              }}
            >
              Permit live commands
            </Button>
          </DialogActions>
        </Dialog>
      </CardContent>
    </Card>
  );
});

export default CircuitBreakerStatusCard;
