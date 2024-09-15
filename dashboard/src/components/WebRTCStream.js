// dashboard/src/components/WebRTCStream.js
import React, { useEffect, useRef } from 'react';
import { websocketVideoFeed } from '../services/apiEndpoints';

const WebRTCStream = ({ protocol = 'http', src }) => {
  const canvasRef = useRef(null);
  const wsRef = useRef(null); // Reference to the WebSocket

  useEffect(() => {
    let isMounted = true; // Flag to track if the component is still mounted

    if (protocol === 'websocket') {
      // Establish WebSocket connection
      const ws = new WebSocket(websocketVideoFeed);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        console.log('WebSocket connection opened');
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        const img = new Image();
        img.onload = () => {
          if (!isMounted) return;
          const ctx = canvasRef.current.getContext('2d');

          // Update canvas dimensions if they differ from the image
          if (
            canvasRef.current.width !== img.width ||
            canvasRef.current.height !== img.height
          ) {
            canvasRef.current.width = img.width;
            canvasRef.current.height = img.height;
          }

          // Clear the canvas and draw the image
          ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
          ctx.drawImage(img, 0, 0, canvasRef.current.width, canvasRef.current.height);
        };
        img.src = URL.createObjectURL(new Blob([event.data], { type: 'image/jpeg' }));
      };

      ws.onerror = (error) => {
        if (!isMounted) return;
        console.error('WebSocket error:', error);
      };

      ws.onclose = () => {
        if (!isMounted) return;
        console.log('WebSocket connection closed');
      };

      // Cleanup on component unmount or protocol change
      return () => {
        isMounted = false;
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close();
          wsRef.current = null;
        }
      };
    } else {
      // Cleanup if protocol changes
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
        wsRef.current = null;
      }
    }
  }, [protocol]);

  if (protocol === 'websocket') {
    return (
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: 'auto' }}
      ></canvas>
    );
  } else if (protocol === 'http') {
    return <img src={src} alt="Live Stream" style={{ width: '100%' }} />;
  }

  return null; // Return null if protocol is not supported
};

export default WebRTCStream;
