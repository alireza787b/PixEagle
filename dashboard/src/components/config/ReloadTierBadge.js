/**
 * ReloadTierBadge - Shows reload tier indicator for config parameters
 *
 * Displays a badge indicating when a parameter change will take effect:
 * - immediate: Changes apply instantly via hot-reload
 * - follower_restart: Requires follower restart
 * - tracker_restart: Requires tracker restart
 * - system_restart: Requires full system restart
 */

import React from 'react';
import PropTypes from 'prop-types';
import { Chip, Tooltip, Box, Typography, Button } from '@mui/material';
import {
  CheckCircle as ImmediateIcon,
  Refresh as RestartIcon,
  Warning as SystemIcon,
  FlightTakeoff as FollowerIcon,
  GpsFixed as TrackerIcon,
} from '@mui/icons-material';

/** Valid reload tier values */
export const RELOAD_TIERS = ['immediate', 'follower_restart', 'tracker_restart', 'system_restart'];

// Tier configuration
const TIER_CONFIG = {
  immediate: {
    label: 'Instant',
    fullLabel: 'Changes apply instantly',
    color: 'success',
    icon: ImmediateIcon,
    description: 'This parameter takes effect immediately after saving. No restart required.',
  },
  follower_restart: {
    label: 'Follower',
    fullLabel: 'Restart follower to apply',
    color: 'warning',
    icon: FollowerIcon,
    description: 'This parameter requires a follower restart to take effect. Click the restart button or start a new follow session.',
    restartEndpoint: '/api/follower/restart',
    restartLabel: 'Restart Follower',
  },
  tracker_restart: {
    label: 'Tracker',
    fullLabel: 'Restart tracker to apply',
    color: 'warning',
    icon: TrackerIcon,
    description: 'This parameter requires a tracker restart to take effect. Click the restart button or switch tracker types.',
    restartEndpoint: '/api/tracker/restart',
    restartLabel: 'Restart Tracker',
  },
  system_restart: {
    label: 'Reboot',
    fullLabel: 'System restart required',
    color: 'error',
    icon: SystemIcon,
    description: 'This parameter requires a full system restart to take effect. Use the Settings > System > Restart button.',
  },
};

/**
 * Get tier config with fallback
 */
const getTierConfig = (tier) => {
  return TIER_CONFIG[tier] || TIER_CONFIG.system_restart;
};

/**
 * Compact badge for table/list views
 * @param {Object} props
 * @param {string} props.tier - The reload tier (immediate, follower_restart, tracker_restart, system_restart)
 * @param {string} [props.size='small'] - Chip size ('small' or 'medium')
 * @param {boolean} [props.showLabel=true] - Whether to show the label text
 */
export const ReloadTierChip = ({ tier, size = 'small', showLabel = true }) => {
  const config = getTierConfig(tier);
  const Icon = config.icon;

  return (
    <Tooltip title={config.description} arrow placement="top">
      <Chip
        size={size}
        icon={<Icon sx={{ fontSize: size === 'small' ? 14 : 18 }} aria-hidden="true" />}
        label={showLabel ? config.label : undefined}
        color={config.color}
        variant="outlined"
        aria-label={`Reload tier: ${config.fullLabel}`}
        sx={{
          height: size === 'small' ? 22 : 28,
          '& .MuiChip-label': {
            px: showLabel ? 0.5 : 0,
            fontSize: size === 'small' ? '0.7rem' : '0.8rem',
          },
          '& .MuiChip-icon': {
            ml: showLabel ? 0.5 : 0,
            mr: showLabel ? -0.25 : 0,
          },
        }}
      />
    </Tooltip>
  );
};

ReloadTierChip.propTypes = {
  tier: PropTypes.oneOf(RELOAD_TIERS),
  size: PropTypes.oneOf(['small', 'medium']),
  showLabel: PropTypes.bool,
};

/**
 * Full badge with description and optional restart button
 * @param {Object} props
 * @param {string} props.tier - The reload tier
 * @param {boolean} [props.showDescription=true] - Whether to show the description text
 * @param {boolean} [props.showRestartButton=false] - Whether to show the restart button
 * @param {Function} [props.onRestart] - Callback when restart button is clicked
 * @param {boolean} [props.compact=false] - If true, renders as ReloadTierChip instead
 */
export const ReloadTierBadge = ({
  tier,
  showDescription = true,
  showRestartButton = false,
  onRestart,
  compact = false
}) => {
  const config = getTierConfig(tier);
  const Icon = config.icon;

  if (compact) {
    return <ReloadTierChip tier={tier} />;
  }

  return (
    <Box
      role="status"
      aria-label={`Reload tier: ${config.fullLabel}`}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        p: 1,
        borderRadius: 1,
        bgcolor: `${config.color}.50`,
        border: 1,
        borderColor: `${config.color}.200`,
      }}
    >
      <Icon color={config.color} aria-hidden="true" />
      <Box sx={{ flex: 1 }}>
        <Typography variant="body2" fontWeight="medium" color={`${config.color}.main`}>
          {config.fullLabel}
        </Typography>
        {showDescription && (
          <Typography variant="caption" color="text.secondary">
            {config.description}
          </Typography>
        )}
      </Box>
      {showRestartButton && config.restartEndpoint && onRestart && (
        <Button
          size="small"
          variant="outlined"
          color={config.color}
          startIcon={<RestartIcon aria-hidden="true" />}
          onClick={() => onRestart(config.restartEndpoint)}
          aria-label={config.restartLabel}
        >
          {config.restartLabel}
        </Button>
      )}
    </Box>
  );
};

ReloadTierBadge.propTypes = {
  tier: PropTypes.oneOf(RELOAD_TIERS),
  showDescription: PropTypes.bool,
  showRestartButton: PropTypes.bool,
  onRestart: PropTypes.func,
  compact: PropTypes.bool,
};

/**
 * Inline indicator for parameter rows
 * Only shows for non-immediate tiers to reduce visual noise
 * @param {Object} props
 * @param {string} props.tier - The reload tier
 */
export const ReloadTierIndicator = ({ tier }) => {
  const config = getTierConfig(tier);
  const Icon = config.icon;

  // Only show for non-immediate tiers to reduce visual noise
  if (tier === 'immediate') {
    return null;
  }

  return (
    <Tooltip title={config.fullLabel} arrow>
      <Icon
        aria-label={config.fullLabel}
        sx={{
          fontSize: 16,
          color: `${config.color}.main`,
          ml: 0.5,
        }}
      />
    </Tooltip>
  );
};

ReloadTierIndicator.propTypes = {
  tier: PropTypes.oneOf(RELOAD_TIERS),
};

/**
 * Get the highest priority tier from a list of tiers
 * @param {string[]} tiers - Array of reload tier values
 * @returns {string} The highest priority tier (system_restart > tracker_restart > follower_restart > immediate)
 */
export const getHighestTier = (tiers) => {
  const priority = {
    system_restart: 4,
    tracker_restart: 3,
    follower_restart: 2,
    immediate: 1,
  };

  // Default to 4 (system_restart) for unknown tiers as safe fallback
  return tiers.reduce((highest, tier) => {
    return (priority[tier] || 4) > (priority[highest] || 4) ? tier : highest;
  }, 'immediate');
};

/**
 * Check if tier requires restart
 * @param {string} tier - The reload tier to check
 * @returns {boolean} True if the tier requires any kind of restart
 */
export const requiresRestart = (tier) => {
  return tier !== 'immediate';
};

// Default export
export default ReloadTierBadge;
