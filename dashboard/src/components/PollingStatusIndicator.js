import React from 'react';
import PropTypes from 'prop-types';
import { Box, Tooltip, Typography } from '@mui/material';
import AccessTimeOutlinedIcon from '@mui/icons-material/AccessTimeOutlined';
import CloudDoneOutlinedIcon from '@mui/icons-material/CloudDoneOutlined';
import CloudOffOutlinedIcon from '@mui/icons-material/CloudOffOutlined';
import PauseCircleOutlineOutlinedIcon from '@mui/icons-material/PauseCircleOutlineOutlined';
import SyncOutlinedIcon from '@mui/icons-material/SyncOutlined';
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';

export const POLLING_STATUS_PRESENTATION = {
  connecting: {
    label: 'Connecting',
    tooltip: 'Waiting for the first telemetry sample',
    color: 'info.main',
    icon: SyncOutlinedIcon,
  },
  active: {
    label: 'Active',
    tooltip: 'The latest telemetry sample reports active operation',
    color: 'success.main',
    icon: CloudDoneOutlinedIcon,
  },
  inactive: {
    label: 'Inactive',
    tooltip: 'The latest telemetry sample reports inactive operation',
    color: 'text.secondary',
    icon: PauseCircleOutlineOutlinedIcon,
  },
  stale: {
    label: 'Stale',
    tooltip: 'The latest telemetry sample is stale',
    color: 'warning.main',
    icon: AccessTimeOutlinedIcon,
  },
  degraded: {
    label: 'Degraded',
    tooltip: 'The latest telemetry sample reports a degraded state',
    color: 'warning.main',
    icon: WarningAmberOutlinedIcon,
  },
  unavailable: {
    label: 'Unavailable',
    tooltip: 'No current telemetry sample is available',
    color: 'error.main',
    icon: CloudOffOutlinedIcon,
  },
};

const PollingStatusIndicator = ({ status }) => {
  const state = POLLING_STATUS_PRESENTATION[status] || POLLING_STATUS_PRESENTATION.unavailable;
  const StatusIcon = state.icon;

  return (
    <Tooltip title={state.tooltip}>
      <Box
        data-testid="telemetry-link-status"
        data-status={status}
        role="status"
        aria-label={`${state.label}. ${state.tooltip}.`}
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.5,
          minWidth: 104,
          height: 24,
          color: state.color,
        }}
      >
        <StatusIcon fontSize="small" />
        <Typography variant="caption" color="inherit" sx={{ fontWeight: 700 }}>
          {state.label}
        </Typography>
      </Box>
    </Tooltip>
  );
};

PollingStatusIndicator.propTypes = {
  status: PropTypes.oneOf([
    'connecting',
    'active',
    'inactive',
    'stale',
    'degraded',
    'unavailable',
  ]).isRequired,
};

export default PollingStatusIndicator;
