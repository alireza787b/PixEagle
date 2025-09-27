// dashboard/src/components/CircuitBreakerStatusCard.js
import React, { useState, useEffect } from 'react';
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

const CircuitBreakerStatusCard = React.memo(() => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);
  const [statistics, setStatistics] = useState(null);
  const [toggling, setToggling] = useState(false);
  const [showStatistics, setShowStatistics] = useState(false);

  const fetchStatus = async () => {
    try {
      const response = await axios.get(endpoints.circuitBreakerStatus);
      setStatus(response.data);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchStatistics = async () => {
    try {
      const response = await axios.get(endpoints.circuitBreakerStats);
      setStatistics(response.data);
    } catch (err) {
      // Note: Error already handled by parent component's error state
      // In production, this would integrate with proper logging service
    }
  };

  const handleToggle = async () => {
    if (toggling) return;

    setToggling(true);
    try {
      const response = await axios.post(endpoints.toggleCircuitBreaker);
      setStatus(prev => ({
        ...prev,
        active: response.data.new_state
      }));
      // Refresh statistics after toggle
      await fetchStatistics();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setToggling(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    // Only fetch statistics initially if user wants to see them
    if (showStatistics) {
      fetchStatistics();
    }

    // Optimized polling: status every 2 seconds, statistics only if shown and less frequently
    const statusInterval = setInterval(fetchStatus, 2000);

    let statisticsInterval = null;
    if (showStatistics) {
      statisticsInterval = setInterval(fetchStatistics, 5000); // Less frequent for statistics
    }

    return () => {
      clearInterval(statusInterval);
      if (statisticsInterval) clearInterval(statisticsInterval);
    };
  }, [showStatistics]); // Re-run when showStatistics changes

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Security color="action" />
            <Typography variant="h6">Circuit Breaker</Typography>
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
            <Typography variant="h6">Circuit Breaker</Typography>
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
            <Typography variant="h6">Circuit Breaker</Typography>
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
          <Typography variant="h6">Circuit Breaker</Typography>
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
                Drone commands are BLOCKED for safety testing
              </Typography>
            </Alert>
          ) : (
            <Alert severity="success" size="small" sx={{ mb: 1 }}>
              <Typography variant="caption">
                Live mode - commands sent to drone
              </Typography>
            </Alert>
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