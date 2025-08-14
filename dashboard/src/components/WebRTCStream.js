// dashboard/src/components/WebRTCStream.js
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { websocketVideoFeed } from '../services/apiEndpoints';
import { Box, Typography, Chip, IconButton, Slider } from '@mui/material';
import { SignalCellular4Bar, SignalCellular2Bar, SignalCellular0Bar, Settings } from '@mui/icons-material';

const WebRTCStream = ({ protocol = 'http', src, showStats = false, showQualityControl = false }) => {
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const [error, setError] = useState(null);
  const [streamStats, setStreamStats] = useState({
    fps: 0,
    quality: 60,
    bandwidth: 0,
    latency: 0,
    frameCount: 0,
    lastFrameTime: 0
  });
  const [quality, setQuality] = useState(60);
  const [showSettings, setShowSettings] = useState(false);
  const frameTimestamps = useRef([]);
  const pendingFrame = useRef(null);
  const heartbeatInterval = useRef(null);

  // Calculate FPS from frame timestamps
  const updateFPS = useCallback(() => {
    const now = Date.now();
    frameTimestamps.current.push(now);
    
    // Keep only last second of timestamps
    frameTimestamps.current = frameTimestamps.current.filter(t => now - t < 1000);
    
    setStreamStats(prev => ({
      ...prev,
      fps: frameTimestamps.current.length,
      frameCount: prev.frameCount + 1
    }));
  }, []);

  // Send quality adjustment request
  const sendQualityRequest = useCallback((newQuality) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'quality',
        quality: newQuality
      }));
      console.log('Quality adjustment requested:', newQuality);
    }
  }, []);

  // Send heartbeat
  const sendHeartbeat = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'ping',
        timestamp: Date.now()
      }));
    }
  }, []);

  useEffect(() => {
    let isMounted = true;

    if (protocol === 'websocket') {
      const ws = new WebSocket(websocketVideoFeed);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        console.log('WebSocket connection opened (optimized protocol)');
        setError(null);
        
        // Start heartbeat
        heartbeatInterval.current = setInterval(sendHeartbeat, 15000);
      };

      ws.onmessage = async (event) => {
        if (!isMounted) return;

        try {
          // Check if this is JSON metadata or binary frame
          if (event.data instanceof ArrayBuffer) {
            // This is the binary frame data
            if (pendingFrame.current) {
              const metadata = pendingFrame.current;
              pendingFrame.current = null;

              // Create image from binary data
              const blob = new Blob([event.data], { type: 'image/jpeg' });
              const img = new Image();
              
              img.onload = () => {
                if (!isMounted || !canvasRef.current) return;
                
                const ctx = canvasRef.current.getContext('2d');
                
                // Update canvas dimensions if needed
                if (canvasRef.current.width !== img.width || 
                    canvasRef.current.height !== img.height) {
                  canvasRef.current.width = img.width;
                  canvasRef.current.height = img.height;
                }
                
                // Draw the image
                ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
                ctx.drawImage(img, 0, 0);
                
                // Update stats
                updateFPS();
                setStreamStats(prev => ({
                  ...prev,
                  quality: metadata.quality || prev.quality,
                  bandwidth: metadata.size ? (metadata.size * 8 / 1024) : prev.bandwidth,
                  lastFrameTime: metadata.timestamp || Date.now()
                }));
                
                // Clean up
                URL.revokeObjectURL(img.src);
              };
              
              img.onerror = () => {
                console.error('Failed to load frame image');
              };
              
              img.src = URL.createObjectURL(blob);
            } else {
              // Legacy mode: direct binary frame without metadata
              const blob = new Blob([event.data], { type: 'image/jpeg' });
              const img = new Image();
              
              img.onload = () => {
                if (!isMounted || !canvasRef.current) return;
                
                const ctx = canvasRef.current.getContext('2d');
                if (canvasRef.current.width !== img.width || 
                    canvasRef.current.height !== img.height) {
                  canvasRef.current.width = img.width;
                  canvasRef.current.height = img.height;
                }
                
                ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
                ctx.drawImage(img, 0, 0);
                updateFPS();
                URL.revokeObjectURL(img.src);
              };
              
              img.src = URL.createObjectURL(blob);
            }
          } else {
            // This is JSON metadata
            const text = await event.data.text();
            const data = JSON.parse(text);
            
            if (data.type === 'frame') {
              // Store metadata for next binary frame
              pendingFrame.current = data;
            } else if (data.type === 'pong') {
              // Calculate latency
              const latency = Date.now() - data.timestamp;
              setStreamStats(prev => ({ ...prev, latency }));
            }
          }
        } catch (err) {
          console.error('Error processing WebSocket message:', err);
        }
      };

      ws.onerror = (errorEvent) => {
        if (!isMounted) return;
        console.error('WebSocket error:', errorEvent);
        setError('Connection error. Retrying...');
        
        // Attempt reconnection after 2 seconds
        setTimeout(() => {
          if (isMounted && wsRef.current?.readyState !== WebSocket.OPEN) {
            console.log('Attempting to reconnect...');
            // Trigger re-render to reconnect
            setError(null);
          }
        }, 2000);
      };

      ws.onclose = () => {
        if (!isMounted) return;
        console.log('WebSocket connection closed');
        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
        }
      };

      return () => {
        isMounted = false;
        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
        }
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close();
          wsRef.current = null;
        }
      };
    } else {
      // HTTP mode cleanup
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
      }
    }
  }, [protocol, updateFPS, sendHeartbeat]);

  // Handle quality slider change
  const handleQualityChange = (event, newValue) => {
    setQuality(newValue);
  };

  const handleQualityCommit = (event, newValue) => {
    sendQualityRequest(newValue);
  };

  // Get signal strength icon based on bandwidth
  const getSignalIcon = () => {
    const kbps = streamStats.bandwidth;
    if (kbps > 500) return <SignalCellular4Bar color="success" />;
    if (kbps > 200) return <SignalCellular2Bar color="warning" />;
    return <SignalCellular0Bar color="error" />;
  };

  if (error) {
    return (
      <Box sx={{ textAlign: 'center', p: 2 }}>
        <Typography color="error">{error}</Typography>
      </Box>
    );
  }

  if (protocol === 'websocket') {
    return (
      <Box sx={{ position: 'relative', width: '100%' }}>
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: 'auto', display: 'block' }}
        />
        
        {/* Streaming Stats Overlay */}
        {showStats && (
          <Box
            sx={{
              position: 'absolute',
              top: 8,
              left: 8,
              backgroundColor: 'rgba(0, 0, 0, 0.7)',
              borderRadius: 1,
              p: 1,
              display: 'flex',
              gap: 1,
              alignItems: 'center'
            }}
          >
            <Chip
              label={`${streamStats.fps} FPS`}
              size="small"
              color={streamStats.fps > 20 ? 'success' : 'warning'}
            />
            <Chip
              label={`Q: ${streamStats.quality}`}
              size="small"
              variant="outlined"
              sx={{ color: 'white', borderColor: 'white' }}
            />
            {getSignalIcon()}
            {streamStats.latency > 0 && (
              <Typography variant="caption" sx={{ color: 'white' }}>
                {streamStats.latency}ms
              </Typography>
            )}
          </Box>
        )}
        
        {/* Quality Control */}
        {showQualityControl && (
          <Box
            sx={{
              position: 'absolute',
              top: 8,
              right: 8,
              backgroundColor: 'rgba(0, 0, 0, 0.7)',
              borderRadius: 1,
              p: 1,
            }}
          >
            <IconButton
              size="small"
              onClick={() => setShowSettings(!showSettings)}
              sx={{ color: 'white' }}
            >
              <Settings />
            </IconButton>
            
            {showSettings && (
              <Box sx={{ width: 200, p: 1 }}>
                <Typography variant="caption" sx={{ color: 'white' }}>
                  Quality: {quality}
                </Typography>
                <Slider
                  value={quality}
                  onChange={handleQualityChange}
                  onChangeCommitted={handleQualityCommit}
                  min={30}
                  max={85}
                  step={5}
                  size="small"
                  sx={{ color: 'white' }}
                />
              </Box>
            )}
          </Box>
        )}
      </Box>
    );
  } else if (protocol === 'http') {
    return <img src={src} alt="Live Stream" style={{ width: '100%', display: 'block' }} />;
  }

  return null;
};

export default WebRTCStream;