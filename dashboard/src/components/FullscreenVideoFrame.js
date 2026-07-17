import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, IconButton, Tooltip } from '@mui/material';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit';

const FullscreenVideoFrame = ({ children }) => {
  const frameRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fullscreenSupported, setFullscreenSupported] = useState(false);
  const [fullscreenError, setFullscreenError] = useState(false);

  useEffect(() => {
    setFullscreenSupported(Boolean(
      document.fullscreenEnabled
      || document.webkitFullscreenEnabled
      || frameRef.current?.requestFullscreen
      || frameRef.current?.webkitRequestFullscreen
    ));

    const updateFullscreenState = () => {
      const activeElement = document.fullscreenElement || document.webkitFullscreenElement;
      setIsFullscreen(activeElement === frameRef.current);
      if (activeElement === frameRef.current) setFullscreenError(false);
    };
    document.addEventListener('fullscreenchange', updateFullscreenState);
    document.addEventListener('webkitfullscreenchange', updateFullscreenState);
    return () => {
      document.removeEventListener('fullscreenchange', updateFullscreenState);
      document.removeEventListener('webkitfullscreenchange', updateFullscreenState);
    };
  }, []);

  const toggleFullscreen = useCallback(async () => {
    try {
      const activeElement = document.fullscreenElement || document.webkitFullscreenElement;
      if (activeElement === frameRef.current) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        if (exit) await exit.call(document);
        return;
      }

      const request = frameRef.current?.requestFullscreen
        || frameRef.current?.webkitRequestFullscreen;
      if (request) await request.call(frameRef.current);
    } catch {
      setFullscreenError(true);
      setFullscreenSupported(false);
    }
  }, []);

  return (
    <Box
      ref={frameRef}
      data-testid="fullscreen-video-frame"
      sx={{
        position: 'relative',
        bgcolor: 'common.black',
        ...(isFullscreen ? { width: '100vw', height: '100vh' } : {}),
      }}
    >
      {typeof children === 'function' ? children({ isFullscreen }) : children}
      <Tooltip title={fullscreenError ? 'Fullscreen unavailable' : isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
        <span
          style={{
            position: 'absolute',
            left: 8,
            bottom: 8,
            zIndex: 14,
          }}
        >
          <IconButton
            aria-label={isFullscreen ? 'Exit fullscreen video' : 'Fullscreen video'}
            size="small"
            disabled={!fullscreenSupported}
            onClick={toggleFullscreen}
            sx={{
              color: 'common.white',
              bgcolor: 'rgba(0, 0, 0, 0.58)',
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.78)' },
            }}
          >
            {isFullscreen ? <FullscreenExitIcon /> : <FullscreenIcon />}
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  );
};

export default FullscreenVideoFrame;
