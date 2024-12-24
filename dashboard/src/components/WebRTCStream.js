// dashboard/src/components/WebRTCStream.js
import React, { useEffect, useRef, useState } from 'react';
import { websocketVideoFeed, webrtcSignalingEndpoint } from '../services/apiEndpoints';

function WebRTCStream({ protocol = 'http', src }) {
  const canvasRef = useRef(null);
  const mjpegWsRef = useRef(null);       // For MJPEG WebSocket
  const signalingWsRef = useRef(null);   // For WebRTC signaling WebSocket
  const pcRef = useRef(null);            // RTCPeerConnection
  const videoRef = useRef(null);
  
  const [error, setError] = useState(null);
  const [isWebSocketOpen, setIsWebSocketOpen] = useState(false);
  const [isSignalingOpen, setIsSignalingOpen] = useState(false);
  
  const isMountedRef = useRef(true);
  const retryCountRef = useRef(0);
  const maxRetryDelay = 30000; // Maximum delay of 30 seconds
  const baseDelay = 1000;       // Start with 1 second

  useEffect(() => {
    // Cleanup on unmount
    return () => {
      isMountedRef.current = false;
      
      // Clean up MJPEG WebSocket
      if (mjpegWsRef.current) {
        console.log('[WebRTCStream] Closing MJPEG WebSocket');
        mjpegWsRef.current.close();
        mjpegWsRef.current = null;
      }
      
      // Clean up signaling WebSocket
      if (signalingWsRef.current) {
        console.log('[WebRTCStream] Closing signaling WebSocket');
        signalingWsRef.current.close();
        signalingWsRef.current = null;
      }
      
      // Clean up PeerConnection
      if (pcRef.current) {
        console.log('[WebRTCStream] Closing PeerConnection');
        pcRef.current.close();
        pcRef.current = null;
      }
    };
  }, []);
  
  // Helper function to establish MJPEG WebSocket with retry
  const connectMjpegWebSocket = () => {
    const attemptConnection = () => {
      if (!isMountedRef.current || protocol !== 'websocket') {
        console.log('[MJPEG WS] Component unmounted or protocol changed. Aborting retry.');
        return;
      }

      console.log(`[MJPEG WS] Attempting to connect. Retry count: ${retryCountRef.current}`);
      const ws = new WebSocket(websocketVideoFeed);
      ws.binaryType = 'arraybuffer';
      mjpegWsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current || protocol !== 'websocket') return;
        console.log('[MJPEG WS] Connection opened to', websocketVideoFeed);
        setIsWebSocketOpen(true);
        retryCountRef.current = 0; // Reset retry count on successful connection
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current || protocol !== 'websocket') return;
        // Uncomment the next line for detailed frame logging
        // console.log('[MJPEG WS] Received a frame chunk. Size:', event.data.byteLength);
        const img = new Image();
        img.onload = () => {
          if (!isMountedRef.current) return;
          if (!canvasRef.current) return;
          const ctx = canvasRef.current.getContext('2d');
          if (!ctx) return;

          if (
            canvasRef.current.width !== img.width ||
            canvasRef.current.height !== img.height
          ) {
            canvasRef.current.width = img.width;
            canvasRef.current.height = img.height;
            console.log('[MJPEG WS] Canvas resized to:', img.width, 'x', img.height);
          }
          ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
          ctx.drawImage(img, 0, 0, canvasRef.current.width, canvasRef.current.height);
        };
        img.onerror = (err) => {
          console.error('[MJPEG WS] Image failed to load from blob:', err);
        };
        img.src = URL.createObjectURL(new Blob([event.data], { type: 'image/jpeg' }));
      };

      ws.onerror = (err) => {
        if (!isMountedRef.current || protocol !== 'websocket') return;
        console.error('[MJPEG WS] WebSocket error:', err);
        // Instead of setting error and aborting, just log and let the retry mechanism handle it
        // setError('Error with WebSocket video stream.');
      };

      ws.onclose = () => {
        if (!isMountedRef.current || protocol !== 'websocket') return;
        console.log('[MJPEG WS] Connection closed. Scheduling reconnection...');
        setIsWebSocketOpen(false);
        retryCountRef.current += 1;
        const delay = Math.min(baseDelay * 2 ** retryCountRef.current, maxRetryDelay);
        console.log(`[MJPEG WS] Reconnecting in ${delay / 1000} seconds...`);
        setTimeout(attemptConnection, delay);
      };
    };

    attemptConnection();
  };

  // Effect for 'websocket' streaming (MJPEG over WS)
  useEffect(() => {
    if (protocol === 'websocket') {
      console.log('[WebRTCStream] Protocol set to "websocket". Initiating connection.');
      connectMjpegWebSocket();

      return () => {
        console.log('[MJPEG WS] Cleaning up...');
        if (mjpegWsRef.current) {
          mjpegWsRef.current.close();
          mjpegWsRef.current = null;
        }
      };
    } else {
      // If we switch away from 'websocket', close the old WebSocket
      if (mjpegWsRef.current) {
        console.log('[MJPEG WS] Protocol changed, closing old WebSocket.');
        mjpegWsRef.current.close();
        mjpegWsRef.current = null;
      }
    }
  }, [protocol]);

  // Effect for 'webrtc' streaming
  useEffect(() => {
    if (protocol !== 'webrtc') return;

    console.log('[WebRTCStream] Protocol set to "webrtc". Setting up WebRTC connection.');
    // Create a local RTCPeerConnection
    const pc = new RTCPeerConnection();
    pcRef.current = pc;

    // Logs for ICE connection changes
    pc.oniceconnectionstatechange = () => {
      console.log('pc.oniceconnectionstatechange ->', pc.iceConnectionState);
      if (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'disconnected') {
        console.warn('ICE connection failed/disconnected. Possibly no video stream will show.');
      }
    };

    // When we get a track from the server, attach it to <video>
    pc.ontrack = (evt) => {
      console.log('pc.ontrack -> got track:', evt);
      if (videoRef.current) {
        console.log('Attaching remote stream to video element.');
        videoRef.current.srcObject = evt.streams[0];
      }
    };

    // Send ICE candidates up to the server
    pc.onicecandidate = (evt) => {
      if (evt.candidate) {
        const msg = {
          type: 'candidate',
          candidate: {
            candidate: evt.candidate.candidate,
            sdpMid: evt.candidate.sdpMid,
            sdpMLineIndex: evt.candidate.sdpMLineIndex,
          },
        };
        if (signalingWsRef.current && signalingWsRef.current.readyState === WebSocket.OPEN) {
          console.log('Sending ICE candidate to server:', msg.candidate);
          signalingWsRef.current.send(JSON.stringify(msg));
        }
      }
    };

    // Connect to /ws/webrtc_signaling
    console.log(`Connecting to signaling endpoint: ${webrtcSignalingEndpoint}`);
    const signalingWS = new WebSocket(webrtcSignalingEndpoint);
    signalingWsRef.current = signalingWS;

    signalingWS.onopen = async () => {
      if (!isMountedRef.current) return;
      console.log('[WebRTC Signaling WS] Connection open. Creating local offer...');
      setIsSignalingOpen(true);
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        console.log('[WebRTC] Local description set. Sending offer to server.');
        const offerMsg = { type: 'offer', sdp: offer.sdp };
        signalingWS.send(JSON.stringify(offerMsg));
      } catch (err) {
        console.error('Error creating WebRTC offer:', err);
        setError('Failed to create WebRTC offer.');
      }
    };

    signalingWS.onerror = (err) => {
      if (!isMountedRef.current) return;
      console.error('Signaling WebSocket error:', err);
      setError('Error with WebRTC signaling WebSocket.');
    };

    signalingWS.onmessage = async (evt) => {
      if (!isMountedRef.current) return;
      console.log('[WebRTC Signaling WS] Received message:', evt.data);
      const message = JSON.parse(evt.data);
      const msgType = message.type;
      if (msgType === 'answer') {
        console.log('Received answer from server. Setting remote desc.');
        const remoteDesc = {
          type: 'answer',
          sdp: message.sdp,
        };
        try {
          await pc.setRemoteDescription(remoteDesc);
          console.log('Remote description set successfully.');
        } catch (err) {
          console.error('Error setting remote desc:', err);
        }
      } else if (msgType === 'candidate') {
        console.log('Received ICE candidate from server:', message.candidate);
        try {
          await pc.addIceCandidate(message.candidate);
          console.log('Candidate added successfully.');
        } catch (err) {
          console.error('Error adding ICE candidate:', err);
        }
      } else {
        console.warn('Unknown signaling message type:', msgType);
      }
    };

    signalingWS.onclose = () => {
      if (!isMountedRef.current) return;
      console.log('Signaling WS closed.');
      setIsSignalingOpen(false);
    };

    return () => {
      console.log('[WebRTCStream] Cleaning up WebRTC effect.');
      signalingWS.close();
      pc.close();
      signalingWsRef.current = null;
      pcRef.current = null;
    };
  }, [protocol]);

  return (
    <>
      {error && <div style={{ color: 'red', position: 'absolute', top: 0, left: 0, zIndex: 10 }}>{error}</div>}
      {protocol === 'websocket' ? (
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: 'auto' }}
        />
      ) : protocol === 'http' ? (
        <img src={src} alt="Live Stream" style={{ width: '100%' }} />
      ) : protocol === 'webrtc' ? (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{ width: '100%', background: '#000' }}
        />
      ) : null}
    </>
  );
}

export default WebRTCStream;
