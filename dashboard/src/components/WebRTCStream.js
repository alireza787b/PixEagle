// dashboard/src/components/WebRTCStream.js
import React, { useEffect, useRef } from 'react';

const WebRTCStream = () => {
  const videoRef = useRef(null);

  useEffect(() => {
    const pc = new RTCPeerConnection();

    pc.ontrack = (event) => {
      if (videoRef.current) {
        videoRef.current.srcObject = event.streams[0];
      }
    };

    const start = async () => {
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        const response = await fetch('http://127.0.0.1:8080/offer', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            sdp: pc.localDescription.sdp,
            type: pc.localDescription.type,
          }),
        });

        if (!response.ok) {
          throw new Error(`Error: ${response.statusText}`);
        }

        const answer = await response.json();
        await pc.setRemoteDescription(new RTCSessionDescription(answer));
      } catch (error) {
        console.error('Error during WebRTC connection setup:', error);
      }
    };

    start();
  }, []);

  return <video ref={videoRef} autoPlay style={{ width: '100%' }} />;
};

export default WebRTCStream;
