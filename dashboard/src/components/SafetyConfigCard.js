// dashboard/src/components/SafetyConfigCard.js
import React from 'react';
import PropTypes from 'prop-types';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  CircularProgress,
  Divider,
  Tooltip,
  Alert
} from '@mui/material';
import {
  Security,
  Speed,
  Height,
  RotateRight,
  CheckCircle,
  Cancel,
  Warning,
  Straighten
} from '@mui/icons-material';
import { useSafetyLimits } from '../hooks/useSafetyConfig';

const LimitRow = ({ icon, label, value, unit, tooltip }) => (
  <Tooltip title={tooltip || ''} placement="left" arrow>
    <Box sx={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      py: 0.5,
      '&:hover': { bgcolor: 'action.hover', borderRadius: 1 }
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {icon}
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
      </Box>
      <Typography variant="body2" fontWeight="medium">
        {value} {unit}
      </Typography>
    </Box>
  </Tooltip>
);

const LimitSection = ({ title, icon, children }) => (
  <Box sx={{ mb: 2 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
      {icon}
      <Typography variant="subtitle2" fontWeight="bold">
        {title}
      </Typography>
    </Box>
    <Box sx={{ pl: 1 }}>
      {children}
    </Box>
  </Box>
);

const SafetyConfigCard = ({ followerName }) => {
  const { limits, loading, error } = useSafetyLimits(followerName);

  if (!followerName) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Security color="action" />
            <Typography variant="h6">Safety Limits</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary">
            Select a follower profile to view safety limits.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  if (loading && !limits) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Security color="action" />
            <Typography variant="h6">Safety Limits</Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Loading limits...</Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (error && !limits) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Security color="error" />
            <Typography variant="h6">Safety Limits</Typography>
          </Box>
          <Alert severity="error" sx={{ mb: 1 }}>
            Failed to load safety limits
          </Alert>
          <Typography variant="caption" color="text.secondary">
            {error}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const { velocity, altitude, rates, altitude_safety_enabled } = limits || {};

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent sx={{ pb: 1 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <Security color="action" />
          <Typography variant="h6">Safety Limits</Typography>
        </Box>

        {/* Follower Name */}
        <Box sx={{ mb: 2 }}>
          <Chip
            label={followerName.replace(/_/g, ' ')}
            size="small"
            color="primary"
            sx={{ fontWeight: 'medium' }}
          />
        </Box>

        <Divider sx={{ mb: 2 }} />

        {/* Velocity Limits */}
        {velocity && (
          <LimitSection title="Velocity Limits" icon={<Speed fontSize="small" color="primary" />}>
            <LimitRow
              icon={<Straighten fontSize="small" sx={{ color: 'text.disabled' }} />}
              label="Forward"
              value={velocity.forward?.toFixed(1)}
              unit="m/s"
              tooltip="Maximum forward velocity"
            />
            <LimitRow
              icon={<Straighten fontSize="small" sx={{ color: 'text.disabled', transform: 'rotate(90deg)' }} />}
              label="Lateral"
              value={velocity.lateral?.toFixed(1)}
              unit="m/s"
              tooltip="Maximum lateral (sideways) velocity"
            />
            <LimitRow
              icon={<Height fontSize="small" sx={{ color: 'text.disabled' }} />}
              label="Vertical"
              value={velocity.vertical?.toFixed(1)}
              unit="m/s"
              tooltip="Maximum vertical velocity"
            />
          </LimitSection>
        )}

        {/* Altitude Limits */}
        {altitude && (
          <LimitSection title="Altitude Limits" icon={<Height fontSize="small" color="success" />}>
            <LimitRow
              icon={<Warning fontSize="small" sx={{ color: 'text.disabled' }} />}
              label="Minimum"
              value={altitude.min?.toFixed(0)}
              unit="m"
              tooltip="Minimum safe altitude"
            />
            <LimitRow
              icon={<Height fontSize="small" sx={{ color: 'text.disabled' }} />}
              label="Maximum"
              value={altitude.max?.toFixed(0)}
              unit="m"
              tooltip="Maximum safe altitude"
            />
            <LimitRow
              icon={<Straighten fontSize="small" sx={{ color: 'text.disabled' }} />}
              label="Warning Buffer"
              value={altitude.warning_buffer?.toFixed(1)}
              unit="m"
              tooltip="Buffer zone for altitude warnings"
            />
            <Box sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              py: 0.5
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Security fontSize="small" sx={{ color: 'text.disabled' }} />
                <Typography variant="body2" color="text.secondary">
                  Safety Enabled
                </Typography>
              </Box>
              <Chip
                icon={altitude_safety_enabled ? <CheckCircle /> : <Cancel />}
                label={altitude_safety_enabled ? 'ON' : 'OFF'}
                color={altitude_safety_enabled ? 'success' : 'error'}
                size="small"
                variant="outlined"
              />
            </Box>
          </LimitSection>
        )}

        {/* Rate Limits */}
        {rates && (
          <LimitSection title="Rate Limits" icon={<RotateRight fontSize="small" color="warning" />}>
            <LimitRow
              icon={<RotateRight fontSize="small" sx={{ color: 'text.disabled' }} />}
              label="Yaw Rate"
              value={rates.yaw_deg?.toFixed(0)}
              unit="deg/s"
              tooltip="Maximum yaw rotation rate"
            />
            {rates.pitch_deg !== undefined && (
              <LimitRow
                icon={<RotateRight fontSize="small" sx={{ color: 'text.disabled', transform: 'rotate(90deg)' }} />}
                label="Pitch Rate"
                value={rates.pitch_deg?.toFixed(0)}
                unit="deg/s"
                tooltip="Maximum pitch rotation rate"
              />
            )}
            {rates.roll_deg !== undefined && (
              <LimitRow
                icon={<RotateRight fontSize="small" sx={{ color: 'text.disabled', transform: 'rotate(45deg)' }} />}
                label="Roll Rate"
                value={rates.roll_deg?.toFixed(0)}
                unit="deg/s"
                tooltip="Maximum roll rotation rate"
              />
            )}
          </LimitSection>
        )}

        {/* Footer */}
        <Box sx={{ mt: 2, pt: 1, borderTop: '1px dashed', borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary">
            Limits from GlobalLimits (auto-refresh 5s)
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

SafetyConfigCard.propTypes = {
  /** Follower profile name (e.g., 'MC_VELOCITY_CHASE', 'FW_ATTITUDE_RATE') */
  followerName: PropTypes.string,
};

SafetyConfigCard.defaultProps = {
  followerName: null,
};

export default SafetyConfigCard;
