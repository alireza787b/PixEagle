// dashboard/src/components/VideoStream.js
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { endpoints, websocketVideoFeed, webrtcSignalingEndpoint } from '../services/apiEndpoints';
import {
  apiFetchJson,
  createDashboardWebSocket,
  getDashboardAuthSession,
  getMediaElementAuthProps,
  isWebSocketAuthClose,
  subscribeDashboardAuthSession,
} from '../services/apiClient';
import { createLatestJpegFrameRenderer } from '../services/latestJpegFrameRenderer';
import { Box, Typography, Chip, IconButton, Slider, CircularProgress } from '@mui/material';
import { SignalCellular4Bar, SignalCellular2Bar, SignalCellular0Bar, Settings, Videocam } from '@mui/icons-material';
import { alpha, useTheme } from '@mui/material/styles';

const WEBRTC_FRAME_TIMEOUT_MS = 8000;
const WEBRTC_DISCONNECT_GRACE_MS = 3000;
const STREAM_SURFACE_SX = {
  position: 'relative',
  width: '100%',
  aspectRatio: '16 / 9',
  minHeight: 0,
  overflow: 'hidden',
  bgcolor: 'grey.900',
  lineHeight: 0,
};
const STREAM_MEDIA_STYLE = {
  width: '100%',
  height: '100%',
  objectFit: 'contain',
  display: 'block',
};

export const browserSupportsWebRTC = () => (
  typeof window !== 'undefined' && typeof window.RTCPeerConnection === 'function'
);

const isLocalBrowserHost = (hostname) => {
  const normalized = String(hostname || '').replace(/^\[|\]$/g, '').toLowerCase();
  return normalized === 'localhost'
    || normalized === '127.0.0.1'
    || normalized === '::1';
};

export const getWebRTCUnsupportedReason = () => {
  if (!browserSupportsWebRTC()) {
    return 'This browser does not support WebRTC video.';
  }
  return null;
};

export const resolveAutoStreamProtocol = ({
  supportsWebRTC = browserSupportsWebRTC(),
  clientConfig = null,
} = {}) => {
  const transports = clientConfig?.transports || {};
  const configuredProtocol = clientConfig?.default_protocol;

  if (configuredProtocol === 'http' && transports.http_mjpeg !== false) {
    return { protocol: 'http', reason: 'configured_http' };
  }
  if (configuredProtocol === 'websocket' && transports.websocket !== false) {
    return { protocol: 'websocket', reason: 'configured_websocket' };
  }
  if (
    configuredProtocol === 'webrtc'
    && supportsWebRTC
    && transports.webrtc !== false
  ) {
    return { protocol: 'webrtc', reason: null };
  }
  if (!supportsWebRTC) {
    return {
      protocol: transports.websocket === false ? 'http' : 'websocket',
      reason: 'webrtc_not_supported',
    };
  }
  if (transports.webrtc !== false) {
    return {
      protocol: 'webrtc',
      reason: null,
    };
  }
  return {
    protocol: transports.websocket === false ? 'http' : 'websocket',
    reason: 'webrtc_disabled',
  };
};

const resolveFallbackProtocol = (clientConfig) => (
  clientConfig?.transports?.websocket === false ? 'http' : 'websocket'
);

const VideoStream = ({
  protocol = 'http',
  src,
  fillContainer = false,
  showStats = false,
  showQualityControl = false,
  onStreamDebugUpdate,
  pageLocationContext,
  clientConfigOverride = null,
}) => {
  const theme = useTheme();
  const streamSurfaceSx = fillContainer
    ? { ...STREAM_SURFACE_SX, height: '100%', aspectRatio: 'auto' }
    : STREAM_SURFACE_SX;
  const [authSession, setAuthSession] = useState(() => getDashboardAuthSession());
  const [clientConfig, setClientConfig] = useState(clientConfigOverride);
  const [clientConfigStatus, setClientConfigStatus] = useState(
    clientConfigOverride ? 'ready' : 'idle'
  );
  const mediaAuthError = authSession.authMode === 'browser_session'
    && (!authSession.authenticated || !authSession.principal?.scopes?.includes('media:read'))
    ? 'Authenticated media session with media:read scope is required.'
    : null;
  // Auto protocol resolution: try WebRTC if available, fallback to WebSocket only after evidence.
  const [autoResolvedProtocol, setAutoResolvedProtocol] = useState(() => (
    protocol === 'auto'
      ? resolveAutoStreamProtocol({ clientConfig: clientConfigOverride }).protocol
      : null
  ));
  const [autoProtocolReason, setAutoProtocolReason] = useState(() => (
    protocol === 'auto'
      ? resolveAutoStreamProtocol({ clientConfig: clientConfigOverride }).reason
      : null
  ));
  const webrtcFrameTimeoutRef = useRef(null);
  const webrtcDisconnectTimeoutRef = useRef(null);

  // Resolve 'auto' to effective protocol
  const effectiveProtocol = protocol === 'auto'
    ? (autoResolvedProtocol || (browserSupportsWebRTC() ? 'webrtc' : 'websocket'))
    : protocol;

  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const [error, setError] = useState(null);
  const [isConnecting, setIsConnecting] = useState(true);
  const [hasReceivedFrame, setHasReceivedFrame] = useState(false);
  const hasReceivedFrameRef = useRef(false);
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
  const bandwidthSamples = useRef([]);
  const pendingFrame = useRef(null);
  const jpegRendererRef = useRef(null);
  const heartbeatInterval = useRef(null);

  // WebSocket reconnection state
  const [reconnectKey, setReconnectKey] = useState(0);
  const reconnectAttempts = useRef(0);
  const websocketReconnectTimeoutRef = useRef(null);

  // WebRTC refs
  const pcRef = useRef(null);
  const sigWsRef = useRef(null);
  const videoRef = useRef(null);
  const webrtcFrameCallbackRef = useRef(null);
  const webrtcStatsIntervalRef = useRef(null);

  const clearWebRTCFrameTimeout = useCallback(() => {
    if (webrtcFrameTimeoutRef.current) {
      clearTimeout(webrtcFrameTimeoutRef.current);
      webrtcFrameTimeoutRef.current = null;
    }
  }, []);

  const clearWebRTCDisconnectTimeout = useCallback(() => {
    if (webrtcDisconnectTimeoutRef.current) {
      clearTimeout(webrtcDisconnectTimeoutRef.current);
      webrtcDisconnectTimeoutRef.current = null;
    }
  }, []);

  const fallbackFromWebRTC = useCallback((reason) => {
    if (protocol !== 'auto') {
      return;
    }
    clearWebRTCFrameTimeout();
    const fallbackProtocol = resolveFallbackProtocol(clientConfig);
    console.warn(`Auto stream protocol falling back to ${fallbackProtocol}: ${reason}`);
    setAutoProtocolReason(reason);
    setAutoResolvedProtocol(prev => (
      prev === 'webrtc' ? fallbackProtocol : prev
    ));
  }, [clearWebRTCFrameTimeout, clientConfig, protocol]);

  const scheduleWebRTCFrameTimeout = useCallback(() => {
    clearWebRTCFrameTimeout();
    if (hasReceivedFrameRef.current) {
      return;
    }

    webrtcFrameTimeoutRef.current = setTimeout(() => {
      webrtcFrameTimeoutRef.current = null;
      if (hasReceivedFrameRef.current) {
        return;
      }

      const reason = `no decoded WebRTC frame within ${WEBRTC_FRAME_TIMEOUT_MS / 1000}s`;
      if (protocol === 'auto') {
        fallbackFromWebRTC(reason);
        return;
      }

      setError(
        `No decoded WebRTC video frame rendered within ${WEBRTC_FRAME_TIMEOUT_MS / 1000} seconds.`
        + ' Check the signaling and ICE path, then retry or select WebSocket.'
      );
      setIsConnecting(false);
    }, WEBRTC_FRAME_TIMEOUT_MS);
  }, [clearWebRTCFrameTimeout, fallbackFromWebRTC, protocol]);

  const handleWebRTCFrameReady = useCallback(() => {
    if (hasReceivedFrameRef.current) {
      return;
    }

    hasReceivedFrameRef.current = true;
    clearWebRTCFrameTimeout();
    setHasReceivedFrame(true);
    setIsConnecting(false);
    setError(null);
  }, [clearWebRTCFrameTimeout]);

  useEffect(() => {
    hasReceivedFrameRef.current = hasReceivedFrame;
  }, [hasReceivedFrame]);

  useEffect(() => (
    subscribeDashboardAuthSession((nextSession) => {
      setAuthSession(nextSession);
    })
  ), []);

  useEffect(() => {
    if (clientConfigOverride) {
      setClientConfig(clientConfigOverride);
      setClientConfigStatus('ready');
      return undefined;
    }
    if (authSession.authMode === null || mediaAuthError) {
      setClientConfigStatus(mediaAuthError ? 'blocked' : 'idle');
      return undefined;
    }

    let active = true;
    setClientConfigStatus('loading');
    apiFetchJson(endpoints.streamingClientConfig)
      .then((payload) => {
        if (!active) return;
        setClientConfig(payload);
        setClientConfigStatus('ready');
      })
      .catch((configError) => {
        if (!active) return;
        const status = configError?.response?.status;
        if (status === 401 || status === 403) {
          setError('Video stream authorization was rejected. Sign in again.');
          setClientConfigStatus('blocked');
          return;
        }
        setClientConfigStatus('error');
        if (protocol === 'auto') {
          setAutoProtocolReason('client_config_unavailable');
          setAutoResolvedProtocol('websocket');
        } else if (protocol === 'webrtc') {
          setError('WebRTC client configuration is unavailable. Select WebSocket or retry.');
          setIsConnecting(false);
        }
      });

    return () => {
      active = false;
    };
  }, [authSession.authMode, clientConfigOverride, mediaAuthError, protocol]);

  // Auto protocol detection. Do not open media until runtime configuration is known.
  useEffect(() => {
    if (protocol !== 'auto') {
      clearWebRTCFrameTimeout();
      setAutoResolvedProtocol(null);
      setAutoProtocolReason(null);
      return undefined;
    }

    if (clientConfigStatus !== 'ready') {
      return undefined;
    }

    const resolution = resolveAutoStreamProtocol({ clientConfig });
    setAutoResolvedProtocol(resolution.protocol);
    setAutoProtocolReason(resolution.reason);

    return () => {
      clearWebRTCFrameTimeout();
    };
  }, [clearWebRTCFrameTimeout, clientConfig, clientConfigStatus, protocol]);

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
      autoProtocolReason,
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
    autoProtocolReason,
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
      if (wsRef.current && (
        wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING
      )) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
      }
      if (websocketReconnectTimeoutRef.current) {
        clearTimeout(websocketReconnectTimeoutRef.current);
        websocketReconnectTimeoutRef.current = null;
      }
      jpegRendererRef.current?.close();
      jpegRendererRef.current = null;
      return;
    }

    let isMounted = true;
    let reconnectScheduled = false;
    let authorizationRejected = false;
    setIsConnecting(true);
    setHasReceivedFrame(false);
    hasReceivedFrameRef.current = false;

    if (mediaAuthError) {
      setError(mediaAuthError);
      setIsConnecting(false);
      return undefined;
    }

    try {
      jpegRendererRef.current = createLatestJpegFrameRenderer(
        canvasRef.current,
        {
          onRender: (metadata = {}) => {
            if (!isMounted) return;
            const now = Date.now();
            const frameSize = Number(metadata.size) || 0;
            bandwidthSamples.current.push({ timestamp: now, bytes: frameSize });
            bandwidthSamples.current = bandwidthSamples.current.filter(
              sample => now - sample.timestamp < 1000
            );
            const bandwidth = bandwidthSamples.current.reduce(
              (sum, sample) => sum + sample.bytes,
              0
            ) * 8 / 1024;

            hasReceivedFrameRef.current = true;
            setHasReceivedFrame(true);
            setIsConnecting(false);
            setError(null);
            updateFPS();
            setStreamStats(prev => ({
              ...prev,
              quality: metadata.quality || prev.quality,
              bandwidth,
              lastFrameTime: metadata.timestamp || now,
            }));
          },
          onError: (decodeError) => {
            if (isMounted) {
              console.error('Failed to decode WebSocket JPEG frame:', decodeError);
            }
          },
        }
      );
    } catch (rendererError) {
      setError(`Video renderer unavailable: ${rendererError.message}`);
      setIsConnecting(false);
      return undefined;
    }

    let ws;
    try {
      ws = createDashboardWebSocket(websocketVideoFeed);
    } catch (authError) {
      jpegRendererRef.current?.close();
      jpegRendererRef.current = null;
      setError(authError.message);
      setIsConnecting(false);
      return undefined;
    }
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

    ws.onmessage = (event) => {
      if (!isMounted) return;

      try {
        if (event.data instanceof ArrayBuffer) {
          const metadata = pendingFrame.current || {};
          pendingFrame.current = null;
          jpegRendererRef.current?.enqueue(event.data, metadata);
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

    const scheduleReconnect = () => {
      if (!isMounted || reconnectScheduled || authorizationRejected) return;
      reconnectScheduled = true;

      const attempts = reconnectAttempts.current;
      reconnectAttempts.current = attempts + 1;
      const backoff = Math.min(2000 * Math.pow(1.5, Math.min(attempts, 5)), 30000);
      const jitter = Math.random() * 1000;
      const delay = backoff + jitter;

      console.log(`Reconnect attempt ${attempts + 1}, waiting ${Math.round(delay)}ms`);
      websocketReconnectTimeoutRef.current = setTimeout(() => {
        websocketReconnectTimeoutRef.current = null;
        if (isMounted) {
          setReconnectKey(prev => prev + 1);
        }
      }, delay);
    };

    ws.onerror = (errorEvent) => {
      if (!isMounted || authorizationRejected) return;
      console.error('WebSocket error:', errorEvent);
      setError('Connection error. Retrying...');
      scheduleReconnect();
    };

    ws.onclose = (event) => {
      if (!isMounted) return;
      console.log('WebSocket connection closed');
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
      }
      if (isWebSocketAuthClose(event)) {
        authorizationRejected = true;
        reconnectScheduled = false;
        if (websocketReconnectTimeoutRef.current) {
          clearTimeout(websocketReconnectTimeoutRef.current);
          websocketReconnectTimeoutRef.current = null;
        }
        setError('Video stream authorization was rejected. Sign in again.');
        setIsConnecting(false);
        return;
      }
      setError('Video connection closed. Retrying...');
      setIsConnecting(true);
      scheduleReconnect();
    };

    return () => {
      isMounted = false;
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
      }
      if (websocketReconnectTimeoutRef.current) {
        clearTimeout(websocketReconnectTimeoutRef.current);
        websocketReconnectTimeoutRef.current = null;
      }
      if (wsRef.current) {
        if (wsRef.current.readyState === WebSocket.OPEN ||
            wsRef.current.readyState === WebSocket.CONNECTING) {
          wsRef.current.close();
        }
        wsRef.current = null;
      }
      jpegRendererRef.current?.close();
      jpegRendererRef.current = null;
      pendingFrame.current = null;
      bandwidthSamples.current = [];
    };
  }, [effectiveProtocol, reconnectKey, updateFPS, sendHeartbeat, mediaAuthError]);

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
      clearWebRTCDisconnectTimeout();
      clearWebRTCFrameTimeout();
      return;
    }

    let isMounted = true;
    let failureHandled = false;
    let sigWs = null;
    const pendingLocalCandidates = [];
    const pendingRemoteCandidates = [];
    let previousInboundStats = null;
    setIsConnecting(true);
    setHasReceivedFrame(false);
    hasReceivedFrameRef.current = false;

    if (mediaAuthError) {
      setError(mediaAuthError);
      setIsConnecting(false);
      return undefined;
    }

    if (clientConfigStatus !== 'ready') {
      if (clientConfigStatus === 'error' || clientConfigStatus === 'blocked') {
        setIsConnecting(false);
      }
      return undefined;
    }

    if (clientConfig?.transports?.webrtc === false) {
      if (protocol === 'auto') {
        fallbackFromWebRTC('webrtc disabled by runtime configuration');
      } else {
        setError('WebRTC is disabled by the running backend configuration.');
        setIsConnecting(false);
      }
      return undefined;
    }

    const unsupportedReason = getWebRTCUnsupportedReason();
    if (unsupportedReason) {
      setError(unsupportedReason);
      setIsConnecting(false);
      return undefined;
    }

    setError(null);

    const pc = new RTCPeerConnection({
      iceServers: clientConfig?.ice_servers || []
    });
    pc.addTransceiver('video', { direction: 'recvonly' });
    pcRef.current = pc;

    const stopFrameMonitor = () => {
      const video = videoRef.current;
      if (
        video
        && webrtcFrameCallbackRef.current !== null
        && typeof video.cancelVideoFrameCallback === 'function'
      ) {
        video.cancelVideoFrameCallback(webrtcFrameCallbackRef.current);
      }
      webrtcFrameCallbackRef.current = null;
      if (webrtcStatsIntervalRef.current) {
        clearInterval(webrtcStatsIntervalRef.current);
        webrtcStatsIntervalRef.current = null;
      }
    };

    const closeWebRTCTransport = () => {
      stopFrameMonitor();
      clearWebRTCDisconnectTimeout();
      clearWebRTCFrameTimeout();
      if (pcRef.current === pc) {
        pc.close();
        pcRef.current = null;
      }
      if (sigWsRef.current === sigWs) {
        if (sigWs && (
          sigWs.readyState === WebSocket.OPEN
          || sigWs.readyState === WebSocket.CONNECTING
        )) {
          sigWs.close();
        }
        sigWsRef.current = null;
      }
      pendingLocalCandidates.length = 0;
    };

    const handleFailure = (reason, message = null, { authRejected = false } = {}) => {
      if (!isMounted || failureHandled) return;
      failureHandled = true;
      closeWebRTCTransport();
      if (authRejected) {
        setError(message || 'WebRTC signaling authorization was rejected. Sign in again.');
        setIsConnecting(false);
        return;
      }
      if (protocol === 'auto') {
        fallbackFromWebRTC(reason);
        return;
      }
      setError(message || `WebRTC video failed: ${reason}.`);
      setIsConnecting(false);
    };

    const noteDecodedWebRTCFrame = () => {
      if (!isMounted) return;
      handleWebRTCFrameReady();
      updateFPS();
      setStreamStats(prev => ({
        ...prev,
        lastFrameTime: Date.now(),
      }));
    };

    const startFrameMonitor = () => {
      const video = videoRef.current;
      if (!video || typeof video.requestVideoFrameCallback !== 'function') {
        return;
      }
      const onFrame = () => {
        if (!isMounted) return;
        noteDecodedWebRTCFrame();
        webrtcFrameCallbackRef.current = video.requestVideoFrameCallback(onFrame);
      };
      webrtcFrameCallbackRef.current = video.requestVideoFrameCallback(onFrame);
    };

    const collectWebRTCStats = async () => {
      if (!isMounted || typeof pc.getStats !== 'function') return;
      try {
        const report = await pc.getStats();
        if (!isMounted) return;
        let inbound = null;
        let roundTripTimeMs = null;
        report.forEach((stat) => {
          if (stat.type === 'inbound-rtp' && stat.kind === 'video' && !stat.isRemote) {
            inbound = stat;
          }
          if (
            stat.type === 'candidate-pair'
            && stat.state === 'succeeded'
            && Number.isFinite(stat.currentRoundTripTime)
          ) {
            roundTripTimeMs = Math.round(stat.currentRoundTripTime * 1000);
          }
        });
        let bandwidth = null;
        if (inbound && previousInboundStats) {
          const elapsedSeconds = (inbound.timestamp - previousInboundStats.timestamp) / 1000;
          const byteDelta = inbound.bytesReceived - previousInboundStats.bytesReceived;
          if (elapsedSeconds > 0 && byteDelta >= 0) {
            bandwidth = byteDelta * 8 / 1024 / elapsedSeconds;
          }
        }
        if (inbound) {
          previousInboundStats = {
            timestamp: inbound.timestamp,
            bytesReceived: inbound.bytesReceived,
          };
        }
        if (bandwidth === null && roundTripTimeMs === null) {
          return;
        }
        setStreamStats(prev => ({
          ...prev,
          bandwidth: bandwidth ?? prev.bandwidth,
          latency: roundTripTimeMs ?? prev.latency,
        }));
      } catch (statsError) {
        console.debug('WebRTC stats unavailable:', statsError);
      }
    };

    const sendLocalIceCandidate = (candidate) => {
      const message = {
        type: 'ice-candidate',
        payload: candidate.toJSON(),
      };
      if (sigWs && sigWs.readyState === WebSocket.OPEN) {
        sigWs.send(JSON.stringify(message));
        return;
      }
      // ICE gathering can begin before the signaling socket reaches OPEN.
      // Keep a bounded queue so candidates are not silently lost.
      if (pendingLocalCandidates.length < 64) {
        pendingLocalCandidates.push(message);
      }
    };

    const flushLocalIceCandidates = () => {
      if (!sigWs || sigWs.readyState !== WebSocket.OPEN) return;
      while (pendingLocalCandidates.length > 0) {
        sigWs.send(JSON.stringify(pendingLocalCandidates.shift()));
      }
    };

    try {
      sigWs = createDashboardWebSocket(webrtcSignalingEndpoint);
    } catch (authError) {
      setError(authError.message);
      setIsConnecting(false);
      pc.close();
      pcRef.current = null;
      return undefined;
    }
    sigWsRef.current = sigWs;

    sigWs.onopen = async () => {
      if (!isMounted) return;
      console.log('WebRTC signaling WebSocket opened');
      setIsConnecting(false);
      scheduleWebRTCFrameTimeout();
      flushLocalIceCandidates();

      try {
        // Create and send offer
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        sigWs.send(JSON.stringify({
          type: 'offer',
          payload: {
            sdp: offer.sdp,
            type: offer.type
          }
        }));
        flushLocalIceCandidates();
        console.log('WebRTC offer sent');
      } catch (err) {
        console.error('Error creating WebRTC offer:', err);
        handleFailure('offer creation failed', `Failed to create WebRTC offer: ${err.message}`);
      }
    };

    sigWs.onmessage = async (event) => {
      if (!isMounted) return;

      try {
        const message = JSON.parse(event.data);

        if (message.type === 'answer') {
          const answer = new RTCSessionDescription(message.payload);
          await pc.setRemoteDescription(answer);
          while (pendingRemoteCandidates.length > 0) {
            await pc.addIceCandidate(pendingRemoteCandidates.shift());
          }
          console.log('WebRTC remote description set');
        } else if (message.type === 'ice-candidate') {
          if (message.payload) {
            const candidatePayload = message.payload.candidate || message.payload;
            const candidate = new RTCIceCandidate(candidatePayload);
            if (pc.remoteDescription) {
              await pc.addIceCandidate(candidate);
            } else {
              pendingRemoteCandidates.push(candidate);
            }
            console.log('WebRTC ICE candidate added');
          }
        } else if (message.type === 'error') {
          handleFailure(
            'signaling server rejected the session',
            message.message || 'WebRTC signaling server rejected the session.'
          );
        }
      } catch (err) {
        console.error('Error handling signaling message:', err);
        handleFailure('invalid signaling response', 'WebRTC signaling negotiation failed.');
      }
    };

    sigWs.onerror = (errorEvent) => {
      if (!isMounted) return;
      console.error('WebRTC signaling WebSocket error:', errorEvent);
      handleFailure('signaling connection error', 'WebRTC signaling connection error.');
    };

    sigWs.onclose = (event) => {
      if (!isMounted) return;
      console.log('WebRTC signaling WebSocket closed');
      if (isWebSocketAuthClose(event)) {
        handleFailure(
          'signaling authorization rejected',
          'WebRTC signaling authorization was rejected. Sign in again.',
          { authRejected: true }
        );
      } else {
        handleFailure(
          'signaling session closed',
          'WebRTC signaling session closed; select Auto to use fallback video.'
        );
      }
    };

    // Handle incoming media track
    pc.ontrack = (event) => {
      if (!isMounted) return;
      console.log('WebRTC track received:', event.track.kind);
      if (videoRef.current && event.streams && event.streams[0]) {
        videoRef.current.srcObject = event.streams[0];
        stopFrameMonitor();
        startFrameMonitor();
        webrtcStatsIntervalRef.current = setInterval(collectWebRTCStats, 1000);
      }
      event.track.onended = () => handleFailure(
        'remote video track ended',
        'WebRTC video track ended; select Auto to use fallback video.'
      );
    };

    // Send ICE candidates to signaling server
    pc.onicecandidate = (event) => {
      if (!isMounted) return;
      if (event.candidate) {
        sendLocalIceCandidate(event.candidate);
      }
    };

    // Handle ICE connection state changes
    pc.oniceconnectionstatechange = () => {
      if (!isMounted) return;
      const state = pc.iceConnectionState;
      console.log('WebRTC ICE connection state:', state);

      if (state === 'failed' || state === 'closed') {
        handleFailure(`ICE connection ${state}`, `WebRTC connection ${state}.`);
      } else if (state === 'disconnected') {
        setError('WebRTC connection interrupted. Recovering...');
        clearWebRTCDisconnectTimeout();
        webrtcDisconnectTimeoutRef.current = setTimeout(() => {
          webrtcDisconnectTimeoutRef.current = null;
          handleFailure(
            'ICE connection remained disconnected',
            'WebRTC connection did not recover; select Auto to use fallback video.'
          );
        }, WEBRTC_DISCONNECT_GRACE_MS);
      } else if (
        (state === 'connected' || state === 'completed')
      ) {
        clearWebRTCDisconnectTimeout();
        if (hasReceivedFrameRef.current) setError(null);
      }
    };

    return () => {
      isMounted = false;
      stopFrameMonitor();
      clearWebRTCDisconnectTimeout();
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
      clearWebRTCFrameTimeout();
    };
  }, [
    clearWebRTCDisconnectTimeout,
    clearWebRTCFrameTimeout,
    clientConfig,
    clientConfigStatus,
    effectiveProtocol,
    fallbackFromWebRTC,
    handleWebRTCFrameReady,
    mediaAuthError,
    protocol,
    scheduleWebRTCFrameTimeout,
    updateFPS,
  ]);

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
          label={`${streamStats.fps} rendered FPS`}
          size="small"
          color={streamStats.fps >= Math.max(1, (clientConfig?.target_fps || 20) * 0.75) ? 'success' : 'warning'}
        />
        {effectiveProtocol === 'websocket' && (
          <Chip
            label={`Q: ${streamStats.quality}`}
            size="small"
            variant="outlined"
            sx={{ color: 'white', borderColor: 'white' }}
          />
        )}
        {getSignalIcon()}
        {streamStats.latency > 0 && (
          <Typography variant="caption" sx={{ color: 'white' }}>
            {streamStats.latency}ms
          </Typography>
        )}
      </Box>
    );
  };

  // JPEG quality is a WebSocket control; WebRTC negotiates its own encoder.
  const renderQualityControl = () => {
    if (!showQualityControl || effectiveProtocol !== 'websocket') return null;
    return (
      <Box
        sx={{
          position: 'absolute',
          bottom: 8,
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

  const renderStreamProtocolBadge = () => {
    if (!['http', 'websocket', 'webrtc'].includes(effectiveProtocol)) {
      return null;
    }
    const transportLabel = effectiveProtocol === 'websocket'
      ? 'WebSocket'
      : effectiveProtocol.toUpperCase();
    let detail = protocol === 'auto' ? 'Auto' : 'Manual';
    if (protocol === 'auto' && autoProtocolReason?.startsWith('configured_')) {
      detail = 'Configured';
    } else if (protocol === 'auto' && effectiveProtocol !== 'webrtc') {
      detail = 'Fallback';
    } else if (
      protocol === 'webrtc'
      && !isLocalBrowserHost(
        pageLocationContext?.hostname
        || (typeof window !== 'undefined' ? window.location.hostname : 'localhost')
      )
    ) {
      detail = 'Remote';
    }

    return (
      <Box
        data-testid="stream-protocol-badge"
        sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          zIndex: 3,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 0.25,
          px: 1,
          py: 0.5,
          maxWidth: 'min(210px, calc(100% - 16px))',
          borderRadius: 0.75,
          bgcolor: alpha(theme.palette.info.main, 0.9),
          color: theme.palette.info.contrastText,
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.28)',
          backdropFilter: 'blur(4px)',
          pointerEvents: 'none',
          lineHeight: 1.15,
          textAlign: 'right',
        }}
      >
        <Typography
          component="span"
          sx={{
            color: 'inherit',
            fontSize: 11,
            fontWeight: 600,
            lineHeight: 1.15,
            overflowWrap: 'anywhere',
          }}
        >
          Video: {transportLabel}
        </Typography>
        <Typography
          component="span"
          sx={{
            color: 'inherit',
            fontSize: 10,
            lineHeight: 1.1,
            opacity: 0.9,
            overflowWrap: 'anywhere',
          }}
        >
          {detail}
        </Typography>
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

  // --- WebSocket protocol ---
  if (effectiveProtocol === 'websocket') {
    return (
      <Box sx={streamSurfaceSx}>
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
            <Box
              role="alert"
              sx={{
                display: 'inline-block',
                maxWidth: 'min(100%, 640px)',
                px: 1,
                py: 0.75,
                border: 1,
                borderColor: 'error.light',
                borderRadius: 1,
                bgcolor: 'rgba(32, 8, 8, 0.9)',
                color: 'error.light',
                fontSize: 11,
                fontWeight: 600,
                lineHeight: 1.35,
                overflowWrap: 'anywhere',
                whiteSpace: 'normal',
              }}
            >
              {error}
            </Box>
          </Box>
        )}

        <canvas
          ref={canvasRef}
          data-video-media="true"
          data-frame-ready={hasReceivedFrame ? 'true' : 'false'}
          style={{
            ...STREAM_MEDIA_STYLE,
            opacity: hasReceivedFrame ? 1 : 0
          }}
        />

        {/* Streaming Stats Overlay */}
        {renderStatsOverlay()}

        {renderStreamProtocolBadge()}

        {/* Quality Control */}
        {renderQualityControl()}
      </Box>
    );
  }

  // --- WebRTC protocol ---
  if (effectiveProtocol === 'webrtc') {
    return (
      <Box sx={streamSurfaceSx}>
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
            <Box
              role="alert"
              sx={{
                display: 'inline-block',
                maxWidth: 'min(100%, 640px)',
                px: 1,
                py: 0.75,
                border: 1,
                borderColor: 'error.light',
                borderRadius: 1,
                bgcolor: 'rgba(32, 8, 8, 0.9)',
                color: 'error.light',
                fontSize: 11,
                fontWeight: 600,
                lineHeight: 1.35,
                overflowWrap: 'anywhere',
                whiteSpace: 'normal',
              }}
            >
              {error}
            </Box>
          </Box>
        )}

        <video
          ref={videoRef}
          data-testid="webrtc-video"
          data-video-media="true"
          data-frame-ready={hasReceivedFrame ? 'true' : 'false'}
          autoPlay
          playsInline
          muted
          onLoadedData={() => {
            handleWebRTCFrameReady();
            if (typeof videoRef.current?.requestVideoFrameCallback !== 'function') {
              updateFPS();
            }
          }}
          style={{
            ...STREAM_MEDIA_STYLE,
            opacity: hasReceivedFrame ? 1 : 0
          }}
        />

        {/* Streaming Stats Overlay */}
        {renderStatsOverlay()}

        {renderStreamProtocolBadge()}

      </Box>
    );
  }

  // --- HTTP protocol ---
  if (effectiveProtocol === 'http') {
    if (mediaAuthError) {
      return (
        <Box sx={{ textAlign: 'center', p: 2 }}>
          <Typography color="error">{mediaAuthError}</Typography>
        </Box>
      );
    }

    return (
      <Box sx={streamSurfaceSx}>
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
          data-video-media="true"
          data-frame-ready={hasReceivedFrame ? 'true' : 'false'}
          {...getMediaElementAuthProps()}
          style={{
            ...STREAM_MEDIA_STYLE,
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
        {renderStreamProtocolBadge()}
      </Box>
    );
  }

  return null;
};

export default VideoStream;
