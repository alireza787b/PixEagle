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
  Button
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
import axios from 'axios';

const NO_CACHE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

const buildNoCacheConfig = () => ({
  headers: NO_CACHE_HEADERS,
  params: { _t: Date.now() },
});

const CircuitBreakerStatusCard = React.memo(() => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);
  const [statistics, setStatistics] = useState(null);
  const [toggling, setToggling] = useState(false);
  const [showStatistics, setShowStatistics] = useState(false);
  const [safetyBypass, setSafetyBypass] = useState(false);
  const [togglingBypass, setTogglingBypass] = useState(false);
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
        setError(err.response?.data?.detail || err.message);
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
        setError(err.response?.data?.detail || err.message);
      }
      return null;
    }
  }, []);

  const handleToggle = async () => {
    if (toggling) return;

    setToggling(true);
    setError(null);
    try {
      await axios.post(endpoints.toggleCircuitBreaker, {}, { headers: NO_CACHE_HEADERS });
      const latestStatus = await fetchStatus({ suppressError: true });
      if (latestStatus && !latestStatus.active) {
        setSafetyBypass(false);
      }

      await fetchStatistics({ suppressError: true });
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
      await fetchStatus({ suppressError: true });
    } finally {
      setToggling(false);
    }
  };

  const handleSafetyBypassToggle = async () => {
    if (togglingBypass) return;

    setTogglingBypass(true);
    setError(null);
    try {
      await axios.post(endpoints.toggleCircuitBreakerSafety, {}, { headers: NO_CACHE_HEADERS });
      await fetchStatus({ suppressError: true });
      await fetchStatistics({ suppressError: true });
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
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
            <Typography variant="h6">🛡️ Circuit Breaker</Typography>
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
            <Typography variant="h6">🛡️ Circuit Breaker</Typography>
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
            <Typography variant="h6">🛡️ Circuit Breaker</Typography>
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
          <Typography variant="h6">🛡️ Circuit Breaker</Typography>
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
                🚫 Drone commands are BLOCKED for safety testing
              </Typography>
            </Alert>
          ) : (
            <Alert severity="success" size="small" sx={{ mb: 1 }}>
              <Typography variant="caption">
                ✅ Live mode - commands sent to drone
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
                    ⚠️ Altitude/velocity safety checks DISABLED for ground testing
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
      </CardContent>
    </Card>
  );
});

export default CircuitBreakerStatusCard;
