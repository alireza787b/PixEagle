import React, { useState, useEffect } from 'react';
import { Card, CardContent, Typography, Box, LinearProgress, Chip } from '@mui/material';
import { Speed, CloudQueue, Warning } from '@mui/icons-material';
import axios from 'axios';

const StreamingStats = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const API_URL = `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`;

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await axios.get(`${API_URL}/stats`);
        setStats(response.data);
        setLoading(false);
      } catch (error) {
        console.error('Failed to fetch streaming stats:', error);
        setLoading(false);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, [API_URL]);

  if (loading || !stats) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Stream Performance
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Loading...
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const dropRate = stats.frames_sent > 0 
    ? ((stats.frames_dropped / stats.frames_sent) * 100).toFixed(1)
    : 0;
  
  const quality = dropRate < 1 ? 'excellent' : dropRate < 5 ? 'good' : 'poor';
  const qualityColor = quality === 'excellent' ? 'success' : quality === 'good' ? 'warning' : 'error';

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Stream Performance
        </Typography>
        
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {/* Connection Status */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Clients:</Typography>
            <Chip 
              icon={<CloudQueue />}
              label={`${stats.http_connections + stats.websocket_connections}`}
              size="small"
              color="primary"
            />
          </Box>

          {/* Frame Stats */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Frames:</Typography>
            <Typography variant="body2" color="textSecondary">
              {stats.frames_sent.toLocaleString()}
            </Typography>
          </Box>

          {/* Drop Rate */}
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
              <Typography variant="body2">Quality:</Typography>
              <Chip 
                label={`${dropRate}% dropped`}
                size="small"
                color={qualityColor}
                icon={dropRate > 5 ? <Warning /> : <Speed />}
              />
            </Box>
            <LinearProgress 
              variant="determinate" 
              value={100 - parseFloat(dropRate)}
              color={qualityColor}
              sx={{ height: 4, borderRadius: 2 }}
            />
          </Box>

          {/* Bandwidth */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Bandwidth:</Typography>
            <Typography variant="body2" color="textSecondary">
              {(stats.total_bandwidth_mb || 0).toFixed(1)} MB
            </Typography>
          </Box>

          {/* Cache Status (if enabled) */}
          {stats.cache_size > 0 && (
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2">Cache:</Typography>
              <Chip 
                label={`${stats.cache_size} frames`}
                size="small"
                variant="outlined"
              />
            </Box>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

export default StreamingStats;