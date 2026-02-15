// dashboard/src/components/VideoStream.js
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { websocketVideoFeed, webrtcSignalingEndpoint } from '../services/apiEndpoints';
import { Box, Typography, Chip, IconButton, Slider, CircularProgress } from '@mui/material';
import { SignalCellular4Bar, SignalCellular2Bar, SignalCellular0Bar, Settings, Videocam } from '@mui/icons-material';
import { alpha, useTheme } from '@mui/material/styles';

const VideoStream = ({
  protocol = 'http',
  src,
  showStats = false,
  showQualityControl = false,
  onStreamDebugUpdate,
}) => {
  const theme = useTheme();
  // Auto protocol resolution: try WebRTC if available, fallback to WebSocket
  const [autoResolvedProtocol, setAutoResolvedProtocol] = useState(null);
  const autoTimeoutRef = useRef(null);

  // Resolve 'auto' to effective protocol
  const effectiveProtocol = protocol === 'auto'
    ? (autoResolvedProtocol || 'websocket')  // Default to websocket while resolving
    : protocol;

  // Auto protocol detection
  useEffect(() => {
    if (protocol !== 'auto') {
      setAutoResolvedProtocol(null);
      return;
    }

    // Check if WebRTC is available in the browser
    if (typeof window !== 'undefined' && window.RTCPeerConnection) {
      setAutoResolvedProtocol('webrtc');

      // If WebRTC doesn't produce a frame within 5 seconds, fall back to WebSocket
      autoTimeoutRef.current = setTimeout(() => {
        setAutoResolvedProtocol(prev => {
          // Only fall back if we haven't received any frames yet
          return prev === 'webrtc' ? 'websocket' : prev;
        });
      }, 5000);
    } else {
      // No WebRTC support, use WebSocket
      setAutoResolvedProtocol('websocket');
    }

    return () => {
      if (autoTimeoutRef.current) {
        clearTimeout(autoTimeoutRef.current);
      }
    };
  }, [protocol]);

  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const [error, setError] = useState(null);
  const [isConnecting, setIsConnecting] = useState(true);
  const [hasReceivedFrame, setHasReceivedFrame] = useState(false);
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
  const lastRenderTime = useRef(0);

  // WebSocket reconnection state
  const [reconnectKey, setReconnectKey] = useState(0);
  const reconnectAttempts = useRef(0);

  // WebRTC refs
  const pcRef = useRef(null);
  const sigWsRef = useRef(null);
  const videoRef = useRef(null);

  const reportDebugInfo = useCallback(() => {
    if (typeof onStreamDebugUpdate !== 'function') {
      return;
    }

    onStreamDebugUpdate({
      requestedProtocol: protocol,
      effectiveProtocol,
      isConnecting,
      hasReceivedFrame,
      error,
      reconnectAttempts: reconnectAttempts.current,
      qualitySetting: quality,
      fps: streamStats.fps,
      streamQuality: streamStats.quality,
      bandwidthKbps: streamStats.bandwidth,
      latencyMs: streamStats.latency,
      frameCount: streamStats.frameCount,
      lastFrameTime: streamStats.lastFrameTime,
      websocketReadyState: wsRef.current ? wsRef.current.readyState : null,
      webrtcIceState: pcRef.current ? pcRef.current.iceConnectionState : null,
      updatedAt: Date.now(),
    });
  }, [
    onStreamDebugUpdate,
    protocol,
    effectiveProtocol,
    isConnecting,
    hasReceivedFrame,
    error,
    quality,
    streamStats.fps,
    streamStats.quality,
    streamStats.bandwidth,
    streamStats.latency,
    streamStats.frameCount,
    streamStats.lastFrameTime,
  ]);

  useEffect(() => {
    reportDebugInfo();
  }, [reportDebugInfo]);

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

  // Send heartbeat with client_timestamp for RTT-based latency
  const sendHeartbeat = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'ping',
        client_timestamp: Date.now()
      }));
    }
  }, []);

  // WebSocket protocol effect
  useEffect(() => {
    if (effectiveProtocol !== 'websocket') {
      // Clean up any existing WebSocket when switching away
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
      }
      return;
    }

    let isMounted = true;
    setIsConnecting(true);
    setHasReceivedFrame(false);

    const ws = new WebSocket(websocketVideoFeed);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMounted) return;
      console.log('WebSocket connection opened (optimized protocol)');
      setError(null);
      setIsConnecting(false);
      reconnectAttempts.current = 0;

      // Start heartbeat
      heartbeatInterval.current = setInterval(sendHeartbeat, 15000);
    };

    ws.onmessage = async (event) => {
      if (!isMounted) return;

      try {
        // Check if this is JSON metadata or binary frame
        if (event.data instanceof ArrayBuffer) {
          // Frame skipping: cap at ~60fps render rate
          const now = performance.now();
          if (now - lastRenderTime.current < 16) {
            // Skip this frame - too soon after last render
            const skippedBlob = new Blob([event.data], { type: 'image/jpeg' });
            const skippedUrl = URL.createObjectURL(skippedBlob);
            URL.revokeObjectURL(skippedUrl);
            pendingFrame.current = null;
            return;
          }

          if (pendingFrame.current) {
            // This is the binary frame data with metadata
            const metadata = pendingFrame.current;
            pendingFrame.current = null;

            // Create image from binary data
            const blob = new Blob([event.data], { type: 'image/jpeg' });
            const img = new Image();

            img.onload = () => {
              if (!isMounted || !canvasRef.current) {
                URL.revokeObjectURL(img.src);
                return;
              }

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
              lastRenderTime.current = performance.now();

              // Mark that we've received at least one frame
              setHasReceivedFrame(true);

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
              URL.revokeObjectURL(img.src);
            };

            img.src = URL.createObjectURL(blob);
          } else {
            // Legacy mode: direct binary frame without metadata
            const blob = new Blob([event.data], { type: 'image/jpeg' });
            const img = new Image();

            img.onload = () => {
              if (!isMounted || !canvasRef.current) {
                URL.revokeObjectURL(img.src);
                return;
              }

              const ctx = canvasRef.current.getContext('2d');
              if (canvasRef.current.width !== img.width ||
                  canvasRef.current.height !== img.height) {
                canvasRef.current.width = img.width;
                canvasRef.current.height = img.height;
              }

              ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
              ctx.drawImage(img, 0, 0);
              lastRenderTime.current = performance.now();
              setHasReceivedFrame(true);
              updateFPS();
              URL.revokeObjectURL(img.src);
            };

            img.onerror = () => {
              console.error('Failed to load legacy frame image');
              URL.revokeObjectURL(img.src);
            };

            img.src = URL.createObjectURL(blob);
          }
        } else {
          // This is JSON metadata (text WebSocket frames arrive as string)
          const data = JSON.parse(event.data);

          if (data.type === 'frame') {
            // Store metadata for next binary frame
            pendingFrame.current = data;
          } else if (data.type === 'pong') {
            // RTT-based latency: use client_timestamp echoed back from server
            const latency = Math.round((Date.now() - data.client_timestamp) / 2);
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

      // Exponential backoff reconnection with jitter
      const attempts = reconnectAttempts.current;
      reconnectAttempts.current = attempts + 1;
      const backoff = Math.min(2000 * Math.pow(1.5, Math.min(attempts, 5)), 30000);
      const jitter = Math.random() * 1000;
      const delay = backoff + jitter;

      console.log(`Reconnect attempt ${attempts + 1}, waiting ${Math.round(delay)}ms`);

      setTimeout(() => {
        if (isMounted) {
          setReconnectKey(prev => prev + 1);
        }
      }, delay);
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
      if (wsRef.current) {
        if (wsRef.current.readyState === WebSocket.OPEN ||
            wsRef.current.readyState === WebSocket.CONNECTING) {
          wsRef.current.close();
        }
        wsRef.current = null;
      }
    };
  }, [effectiveProtocol, reconnectKey, updateFPS, sendHeartbeat]);

  // WebRTC protocol effect
  useEffect(() => {
    if (effectiveProtocol !== 'webrtc') {
      // Clean up any existing WebRTC resources when switching away
      if (pcRef.current) {
        pcRef.current.close();
        pcRef.current = null;
      }
      if (sigWsRef.current) {
        if (sigWsRef.current.readyState === WebSocket.OPEN ||
            sigWsRef.current.readyState === WebSocket.CONNECTING) {
          sigWsRef.current.close();
        }
        sigWsRef.current = null;
      }
      return;
    }

    let isMounted = true;
    setIsConnecting(true);
    setHasReceivedFrame(false);
    setError(null);

    // Create RTCPeerConnection
    const pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
    });
    pcRef.current = pc;

    // Open signaling WebSocket
    const sigWs = new WebSocket(webrtcSignalingEndpoint);
    sigWsRef.current = sigWs;

    sigWs.onopen = async () => {
      if (!isMounted) return;
      console.log('WebRTC signaling WebSocket opened');
      setIsConnecting(false);

      try {
        // Create and send offer
        const offer = await pc.createOffer({ offerToReceiveVideo: true });
        await pc.setLocalDescription(offer);

        sigWs.send(JSON.stringify({
          type: 'offer',
          payload: {
            sdp: offer.sdp,
            type: offer.type
          }
        }));
        console.log('WebRTC offer sent');
      } catch (err) {
        console.error('Error creating WebRTC offer:', err);
        if (isMounted) {
          setError('Failed to create WebRTC offer: ' + err.message);
        }
      }
    };

    sigWs.onmessage = async (event) => {
      if (!isMounted) return;

      try {
        const message = JSON.parse(event.data);

        if (message.type === 'answer') {
          // Set remote description from server answer
          const answer = new RTCSessionDescription(message.payload);
          await pc.setRemoteDescription(answer);
          console.log('WebRTC remote description set');
        } else if (message.type === 'ice-candidate') {
          // Add ICE candidate from server
          if (message.payload) {
            const candidate = new RTCIceCandidate(message.payload);
            await pc.addIceCandidate(candidate);
            console.log('WebRTC ICE candidate added');
          }
        }
      } catch (err) {
        console.error('Error handling signaling message:', err);
      }
    };

    sigWs.onerror = (errorEvent) => {
      if (!isMounted) return;
      console.error('WebRTC signaling WebSocket error:', errorEvent);
      setError('WebRTC signaling connection error');
    };

    sigWs.onclose = () => {
      if (!isMounted) return;
      console.log('WebRTC signaling WebSocket closed');
    };

    // Handle incoming media track
    pc.ontrack = (event) => {
      if (!isMounted) return;
      console.log('WebRTC track received:', event.track.kind);
      if (videoRef.current && event.streams && event.streams[0]) {
        videoRef.current.srcObject = event.streams[0];
        setHasReceivedFrame(true);
        // Cancel auto-fallback timeout since WebRTC is working
        if (autoTimeoutRef.current) {
          clearTimeout(autoTimeoutRef.current);
          autoTimeoutRef.current = null;
        }
      }
    };

    // Send ICE candidates to signaling server
    pc.onicecandidate = (event) => {
      if (!isMounted) return;
      if (event.candidate && sigWs.readyState === WebSocket.OPEN) {
        sigWs.send(JSON.stringify({
          type: 'ice-candidate',
          payload: event.candidate.toJSON()
        }));
      }
    };

    // Handle ICE connection state changes
    pc.oniceconnectionstatechange = () => {
      if (!isMounted) return;
      const state = pc.iceConnectionState;
      console.log('WebRTC ICE connection state:', state);

      if (state === 'failed' || state === 'disconnected') {
        setError('WebRTC connection ' + state + '. Please retry.');
        setHasReceivedFrame(false);
      } else if (state === 'connected' || state === 'completed') {
        setError(null);
      }
    };

    return () => {
      isMounted = false;
      if (pcRef.current) {
        pcRef.current.close();
        pcRef.current = null;
      }
      if (sigWsRef.current) {
        if (sigWsRef.current.readyState === WebSocket.OPEN ||
            sigWsRef.current.readyState === WebSocket.CONNECTING) {
          sigWsRef.current.close();
        }
        sigWsRef.current = null;
      }
    };
  }, [effectiveProtocol]);

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

  // Stats overlay component (shared between websocket and webrtc)
  const renderStatsOverlay = () => {
    if (!showStats) return null;
    return (
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
    );
  };

  // Quality control overlay component (shared between websocket and webrtc)
  const renderQualityControl = () => {
    if (!showQualityControl) return null;
    return (
      <Box
        sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === 'dark' ? 0.72 : 0.82),
          border: '1px solid',
          borderColor: 'divider',
          backdropFilter: 'blur(6px)',
          borderRadius: 1,
          p: 1,
        }}
      >
        <IconButton
          size="small"
          onClick={() => setShowSettings(!showSettings)}
          sx={{ color: 'text.primary' }}
        >
          <Settings />
        </IconButton>

        {showSettings && (
          <Box sx={{ width: 200, p: 1 }}>
            <Typography variant="caption" sx={{ color: 'text.primary' }}>
              Quality: {quality}
            </Typography>
            <Slider
              value={quality}
              onChange={handleQualityChange}
              onChangeCommitted={handleQualityCommit}
              min={20}
              max={95}
              step={5}
              size="small"
              sx={{
                color: 'primary.main',
                '& .MuiSlider-valueLabel': {
                  bgcolor: 'background.paper',
                  color: 'text.primary',
                  border: '1px solid',
                  borderColor: 'divider',
                },
              }}
            />
          </Box>
        )}
      </Box>
    );
  };

  // Loading/connecting placeholder component
  const renderLoadingPlaceholder = () => {
    if (hasReceivedFrame) return null;
    return (
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'grey.400',
          minHeight: 200,
          zIndex: 1
        }}
      >
        {isConnecting ? (
          <>
            <CircularProgress size={40} sx={{ color: 'grey.500', mb: 2 }} />
            <Typography variant="body2">Connecting to video stream...</Typography>
          </>
        ) : (
          <>
            <Videocam sx={{ fontSize: 48, mb: 1, opacity: 0.5 }} />
            <Typography variant="body2">Waiting for video frames...</Typography>
          </>
        )}
      </Box>
    );
  };

  // Error display (non-blocking for reconnecting WebSocket, blocking for fatal errors)
  if (error && effectiveProtocol !== 'websocket') {
    return (
      <Box sx={{ textAlign: 'center', p: 2 }}>
        <Typography color="error">{error}</Typography>
      </Box>
    );
  }

  // --- WebSocket protocol ---
  if (effectiveProtocol === 'websocket') {
    return (
      <Box sx={{ position: 'relative', width: '100%', bgcolor: 'grey.900', lineHeight: 0 }}>
        {/* Loading/Connecting Placeholder */}
        {renderLoadingPlaceholder()}

        {/* Error overlay for WebSocket (non-blocking, shows while reconnecting) */}
        {error && (
          <Box
            sx={{
              position: 'absolute',
              bottom: 8,
              left: 8,
              right: 8,
              zIndex: 2,
              textAlign: 'center'
            }}
          >
            <Chip
              label={error}
              color="error"
              size="small"
              variant="outlined"
            />
          </Box>
        )}

        <canvas
          ref={canvasRef}
          style={{
            width: '100%',
            height: 'auto',
            display: 'block',
            opacity: hasReceivedFrame ? 1 : 0
          }}
        />

        {/* Streaming Stats Overlay */}
        {renderStatsOverlay()}

        {/* Quality Control */}
        {renderQualityControl()}
      </Box>
    );
  }

  // --- WebRTC protocol ---
  if (effectiveProtocol === 'webrtc') {
    return (
      <Box sx={{ position: 'relative', width: '100%', bgcolor: 'grey.900', lineHeight: 0 }}>
        {/* Loading/Connecting Placeholder */}
        {renderLoadingPlaceholder()}

        {/* Error overlay for WebRTC */}
        {error && (
          <Box
            sx={{
              position: 'absolute',
              bottom: 8,
              left: 8,
              right: 8,
              zIndex: 2,
              textAlign: 'center'
            }}
          >
            <Chip
              label={error}
              color="error"
              size="small"
              variant="outlined"
            />
          </Box>
        )}

        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{
            width: '100%',
            height: 'auto',
            display: 'block',
            opacity: hasReceivedFrame ? 1 : 0
          }}
        />

        {/* Streaming Stats Overlay */}
        {renderStatsOverlay()}

        {/* Quality Control */}
        {renderQualityControl()}
      </Box>
    );
  }

  // --- HTTP protocol ---
  if (effectiveProtocol === 'http') {
    return (
      <Box sx={{ position: 'relative', width: '100%', bgcolor: 'grey.900', lineHeight: 0 }}>
        {/* Loading spinner before image loads */}
        {!hasReceivedFrame && (
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'grey.400',
              minHeight: 200,
              zIndex: 1
            }}
          >
            {error ? (
              <>
                <Videocam sx={{ fontSize: 48, mb: 1, opacity: 0.5, color: 'error.main' }} />
                <Typography variant="body2" color="error">{error}</Typography>
              </>
            ) : (
              <>
                <CircularProgress size={40} sx={{ color: 'grey.500', mb: 2 }} />
                <Typography variant="body2">Loading video stream...</Typography>
              </>
            )}
          </Box>
        )}

        <img
          src={src}
          alt="Live Stream"
          style={{
            width: '100%',
            display: 'block',
            opacity: hasReceivedFrame ? 1 : 0
          }}
          onLoad={() => {
            setHasReceivedFrame(true);
            setError(null);
          }}
          onError={() => {
            setError('Failed to load HTTP video stream. Check the source URL.');
            setHasReceivedFrame(false);
          }}
        />
      </Box>
    );
  }

  return null;
};

export default VideoStream;
