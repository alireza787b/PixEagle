import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import VideoStream, {
  getWebRTCUnsupportedReason,
  resolveAutoStreamProtocol,
} from './VideoStream';
import * as apiClient from '../services/apiClient';
import {
  clearDashboardAuthSession,
  setDashboardAuthSession,
} from '../services/apiClient';

jest.mock('../services/latestJpegFrameRenderer', () => ({
  createLatestJpegFrameRenderer: jest.fn(() => ({
    enqueue: jest.fn(),
    close: jest.fn(),
  })),
}));

const STREAMING_CLIENT_CONFIG = {
  streaming_enabled: true,
  default_protocol: 'auto',
  target_fps: 20,
  transports: { webrtc: true, websocket: true, http_mjpeg: true },
  ice_servers: [{ urls: 'stun:stun.example.test:3478' }],
};

describe('VideoStream browser-session media authorization', () => {
  const originalWebSocket = global.WebSocket;
  const originalRTCPeerConnection = global.RTCPeerConnection;
  const originalMediaStream = global.MediaStream;

  beforeEach(() => {
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    clearDashboardAuthSession(null);
    jest.spyOn(apiClient, 'apiFetchJson').mockResolvedValue(STREAMING_CLIENT_CONFIG);
  });

  afterEach(() => {
    jest.restoreAllMocks();
    global.WebSocket = originalWebSocket;
    global.RTCPeerConnection = originalRTCPeerConnection;
    global.MediaStream = originalMediaStream;
    jest.useRealTimers();
  });

  const installMockWebSocket = () => {
    const sockets = [];
    function MockWebSocket(url) {
      this.url = url;
      this.readyState = MockWebSocket.CONNECTING;
      this.close = jest.fn(() => {
        this.readyState = MockWebSocket.CLOSED;
      });
      this.send = jest.fn();
      sockets.push(this);
    }
    MockWebSocket.CONNECTING = 0;
    MockWebSocket.OPEN = 1;
    MockWebSocket.CLOSED = 3;
    global.WebSocket = jest.fn((url) => new MockWebSocket(url));
    Object.assign(global.WebSocket, {
      CONNECTING: MockWebSocket.CONNECTING,
      OPEN: MockWebSocket.OPEN,
      CLOSED: MockWebSocket.CLOSED,
    });
    return sockets;
  };

  const installMockPeerConnection = () => {
    const peers = [];
    function MockRTCPeerConnection() {
      this.addTransceiver = jest.fn();
      this.createOffer = jest.fn().mockResolvedValue({ type: 'offer', sdp: 'mock-offer' });
      this.localDescription = null;
      this.setLocalDescription = jest.fn().mockImplementation(async (description) => {
        this.localDescription = {
          ...description,
          sdp: 'mock-local-description',
        };
      });
      this.setRemoteDescription = jest.fn().mockImplementation(async (description) => {
        this.remoteDescription = description;
      });
      this.addIceCandidate = jest.fn().mockResolvedValue(undefined);
      this.getStats = jest.fn().mockResolvedValue(new Map());
      this.close = jest.fn();
      this.iceConnectionState = 'new';
      this.remoteDescription = null;
      peers.push(this);
    }
    global.RTCPeerConnection = jest.fn(() => new MockRTCPeerConnection());
    global.RTCSessionDescription = jest.fn((payload) => payload);
    global.RTCIceCandidate = jest.fn((payload) => payload);
    return peers;
  };

  const renderVideo = (props = {}) => render(
    <VideoStream
      clientConfigOverride={STREAMING_CLIENT_CONFIG}
      {...props}
    />
  );

  test('auto protocol resolver tries WebRTC on local and remote pages', () => {
    expect(resolveAutoStreamProtocol({
      supportsWebRTC: true,
      clientConfig: STREAMING_CLIENT_CONFIG,
    })).toEqual({
      protocol: 'webrtc',
      reason: null,
    });
    expect(resolveAutoStreamProtocol({
      supportsWebRTC: true,
      clientConfig: {
        ...STREAMING_CLIENT_CONFIG,
        transports: { ...STREAMING_CLIENT_CONFIG.transports, webrtc: false },
      },
    })).toEqual({
      protocol: 'websocket',
      reason: 'webrtc_disabled',
    });
    expect(resolveAutoStreamProtocol({
      supportsWebRTC: false,
      clientConfig: STREAMING_CLIENT_CONFIG,
    })).toEqual({
      protocol: 'websocket',
      reason: 'webrtc_not_supported',
    });
  });

  test('manual WebRTC remains an explicit lab option on public HTTP', () => {
    global.RTCPeerConnection = jest.fn();

    expect(getWebRTCUnsupportedReason({
      protocol: 'http:',
      hostname: '203.0.113.45',
    })).toBeNull();
    expect(getWebRTCUnsupportedReason({
      protocol: 'http:',
      hostname: 'localhost',
    })).toBeNull();
    expect(getWebRTCUnsupportedReason({
      protocol: 'https:',
      hostname: 'pixeagle.example',
    })).toBeNull();
  });

  test('auto protocol attempts WebRTC for public HTTP demos', async () => {
    installMockWebSocket();
    installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({
      protocol: 'auto',
      pageLocationContext: { protocol: 'http:', hostname: '203.0.113.45' },
    });

    const badge = await screen.findByTestId('stream-protocol-badge');
    expect(badge).toHaveTextContent('Video: WEBRTC');
    expect(badge).toHaveTextContent('Auto');
    expect(global.RTCPeerConnection).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(global.WebSocket).toHaveBeenCalledTimes(1);
    });
  });

  test('manual WebRTC public HTTP/IP demo attempts signaling with a remote badge', async () => {
    installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({
      protocol: 'webrtc',
      pageLocationContext: { protocol: 'http:', hostname: '203.0.113.45' },
    });

    const badge = await screen.findByTestId('stream-protocol-badge');
    expect(badge).toHaveTextContent('Video: WEBRTC');
    expect(badge).toHaveTextContent('Remote');
    expect(global.RTCPeerConnection).toHaveBeenCalledTimes(1);
    expect(global.WebSocket).toHaveBeenCalledTimes(1);
    expect(peers[0].addTransceiver).toHaveBeenCalledWith('video', { direction: 'recvonly' });
  });

  test('creates a standards-based recvonly WebRTC offer', async () => {
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'webrtc' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      sockets[0].onopen();
    });

    expect(peers[0].addTransceiver).toHaveBeenCalledWith('video', { direction: 'recvonly' });
    expect(peers[0].createOffer).toHaveBeenCalledWith();
    expect(sockets[0].send).toHaveBeenCalledWith(expect.stringContaining('"offer"'));
    expect(sockets[0].send).toHaveBeenCalledWith(
      expect.stringContaining('"sdp":"mock-local-description"')
    );
  });

  test('keeps the media deadline active when a track arrives before ICE connects', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({
      protocol: 'webrtc',
      pageLocationContext: { protocol: 'http:', hostname: '203.0.113.45' },
    });

    await waitFor(() => {
      expect(global.RTCPeerConnection).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      sockets[0].onopen();
    });

    const video = screen.getByTestId('webrtc-video');
    await act(async () => {
      await sockets[0].onmessage({
        data: JSON.stringify({
          type: 'answer',
          payload: { type: 'answer', sdp: 'mock-answer' },
        }),
      });
    });
    act(() => {
      peers[0].ontrack({
        track: { kind: 'video' },
        streams: [{ id: 'mock-stream' }],
      });
    });

    expect(video).toHaveAttribute('data-frame-ready', 'false');
    expect(screen.getByText('Waiting for video frames...')).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(14999);
    });
    expect(screen.queryByText(/No decoded WebRTC video frame rendered/)).not.toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(screen.getByRole('alert')).toHaveTextContent(/media connection did not complete/);
    expect(peers[0].close).toHaveBeenCalledTimes(1);
    expect(sockets[0].close).toHaveBeenCalledTimes(1);
  });

  test('starts the decoded-frame deadline only after ICE and a video track are ready', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'webrtc' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));
    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      sockets[0].onopen();
      await sockets[0].onmessage({
        data: JSON.stringify({
          type: 'answer',
          payload: { type: 'answer', sdp: 'mock-answer' },
        }),
      });
    });
    act(() => {
      peers[0].ontrack({
        track: { kind: 'video' },
        streams: [{ id: 'mock-stream' }],
      });
      peers[0].iceConnectionState = 'connected';
      peers[0].oniceconnectionstatechange();
    });

    act(() => {
      jest.advanceTimersByTime(9999);
    });
    expect(screen.queryByText(/No decoded WebRTC video frame rendered/)).not.toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(1);
    });
    const recoveryMessage = screen.getByRole('alert');
    expect(recoveryMessage).toHaveTextContent(/No decoded WebRTC video frame rendered within 10 seconds/);
    expect(recoveryMessage).toHaveTextContent(/select WebSocket/);
    expect(recoveryMessage).toHaveStyle({ whiteSpace: 'normal' });
    expect(peers[0].close).toHaveBeenCalledTimes(1);
    expect(sockets[0].close).toHaveBeenCalledTimes(1);
  });

  test('assembles a MediaStream when a browser emits a streamless video track', async () => {
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    const assembledStream = { id: 'assembled-stream' };
    global.MediaStream = jest.fn(() => assembledStream);
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'webrtc' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));
    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      await sockets[0].onopen();
      await sockets[0].onmessage({
        data: JSON.stringify({
          type: 'answer',
          payload: { type: 'answer', sdp: 'mock-answer' },
        }),
      });
    });

    const track = { kind: 'video' };
    act(() => {
      peers[0].ontrack({ track, streams: [] });
    });

    expect(global.MediaStream).toHaveBeenCalledWith([track]);
    expect(screen.getByTestId('webrtc-video').srcObject).toBe(assembledStream);
  });

  test('does not send or re-arm negotiation after teardown during offer creation', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    const { unmount } = renderVideo({ protocol: 'webrtc' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));
    let resolveOffer;
    peers[0].createOffer.mockReturnValue(new Promise((resolve) => {
      resolveOffer = resolve;
    }));
    sockets[0].readyState = global.WebSocket.OPEN;
    let openPromise;
    act(() => {
      openPromise = sockets[0].onopen();
    });

    unmount();
    await act(async () => {
      resolveOffer({ type: 'offer', sdp: 'late-offer' });
      await openPromise;
    });

    expect(sockets[0].send).not.toHaveBeenCalled();
    expect(jest.getTimerCount()).toBe(0);
  });

  test('blocks websocket video when browser session lacks media read scope', async () => {
    global.WebSocket = jest.fn();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: false,
      principal: { scopes: [] },
    });

    renderVideo({ protocol: 'websocket' });

    expect(await screen.findByText(/Authenticated media session with media:read scope is required/)).toBeInTheDocument();
    expect(global.WebSocket).not.toHaveBeenCalled();
  });

  test('closes active websocket video when browser session loses media read access', async () => {
    const sockets = installMockWebSocket();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'websocket' });

    await waitFor(() => {
      expect(global.WebSocket).toHaveBeenCalledTimes(1);
    });

    act(() => {
      setDashboardAuthSession({
        auth_mode: 'browser_session',
        authenticated: false,
        principal: { scopes: [] },
      });
    });

    expect(await screen.findByText(/Authenticated media session with media:read scope is required/)).toBeInTheDocument();
    expect(sockets[0].close).toHaveBeenCalledTimes(1);
  });

  test('shows explicit operator guidance when websocket auth is rejected', async () => {
    const sockets = installMockWebSocket();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'websocket' });

    await waitFor(() => {
      expect(global.WebSocket).toHaveBeenCalledTimes(1);
    });

    act(() => {
      sockets[0].onclose({ code: 1008 });
    });

    expect(await screen.findByText('Video stream authorization was rejected. Sign in again.')).toBeInTheDocument();

    jest.useFakeTimers();
    act(() => {
      jest.advanceTimersByTime(60000);
    });
    expect(global.WebSocket).toHaveBeenCalledTimes(1);
  });

  test('reconnects after a clean non-auth websocket close', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'websocket' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    act(() => sockets[0].onclose({ code: 1000 }));
    expect(screen.getByText('Video connection closed. Retrying...')).toBeInTheDocument();

    act(() => jest.advanceTimersByTime(4000));
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(2));
  });

  test('cancels an error retry when the socket then closes for authorization', async () => {
    jest.useFakeTimers();
    jest.spyOn(console, 'error').mockImplementation(() => {});
    const sockets = installMockWebSocket();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'websocket' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    act(() => {
      sockets[0].onerror(new Event('error'));
      sockets[0].onclose({ code: 1008 });
    });
    expect(screen.getByText('Video stream authorization was rejected. Sign in again.')).toBeInTheDocument();

    act(() => jest.advanceTimersByTime(60000));
    expect(global.WebSocket).toHaveBeenCalledTimes(1);
  });

  test('does not retry when an error arrives after an authorization close', async () => {
    jest.useFakeTimers();
    jest.spyOn(console, 'error').mockImplementation(() => {});
    const sockets = installMockWebSocket();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'websocket' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    act(() => {
      sockets[0].onclose({ code: 1008 });
      sockets[0].onerror(new Event('error'));
    });
    expect(screen.getByText('Video stream authorization was rejected. Sign in again.')).toBeInTheDocument();

    act(() => jest.advanceTimersByTime(60000));
    expect(global.WebSocket).toHaveBeenCalledTimes(1);
  });

  test('blocks webrtc setup when browser session lacks media read scope', async () => {
    global.WebSocket = jest.fn();
    global.RTCPeerConnection = jest.fn();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['actions:execute'] },
    });

    renderVideo({ protocol: 'webrtc' });

    expect(await screen.findByText(/Authenticated media session with media:read scope is required/)).toBeInTheDocument();
    expect(global.RTCPeerConnection).not.toHaveBeenCalled();
    expect(global.WebSocket).not.toHaveBeenCalled();
  });

  test('blocks HTTP media loading when browser session lacks media read scope', async () => {
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['actions:execute'] },
    });

    renderVideo({ protocol: 'http', src: 'http://192.168.10.2:5077/video_feed' });

    expect(await screen.findByText(/Authenticated media session with media:read scope is required/)).toBeInTheDocument();
    expect(screen.queryByAltText('Live Stream')).not.toBeInTheDocument();
  });

  test('uses credentialed HTTP media loading in browser-session mode', () => {
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'http', src: 'http://192.168.10.2:5077/video_feed' });

    expect(screen.getByAltText('Live Stream')).toHaveAttribute('crossorigin', 'use-credentials');
  });

  test('hides the routine transport badge with operator overlays disabled', () => {
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({
      protocol: 'http',
      src: 'http://192.168.10.2:5077/video_feed',
      showOperatorOverlays: false,
    });

    expect(screen.queryByTestId('stream-protocol-badge')).not.toBeInTheDocument();
    expect(screen.getByAltText('Live Stream')).toBeInTheDocument();
  });

  test('auto protocol starts with WebRTC and waits before websocket fallback', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'auto' });

    await waitFor(() => {
      expect(global.RTCPeerConnection).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));
    expect(sockets[0].url).toContain('/ws/webrtc_signaling');
    expect(sockets.map((socket) => socket.url)).not.toContainEqual(expect.stringContaining('/ws/video_feed'));

    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      sockets[0].onopen();
    });
    expect(sockets[0].send).toHaveBeenCalledWith(expect.stringContaining('"offer"'));

    act(() => {
      jest.advanceTimersByTime(11999);
    });
    expect(global.WebSocket).toHaveBeenCalledTimes(1);

    act(() => {
      jest.advanceTimersByTime(1);
    });

    await waitFor(() => {
      expect(global.WebSocket).toHaveBeenCalledTimes(2);
    });
    expect(sockets[1].url).toContain('/ws/video_feed');
  });

  test('auto protocol falls back when WebRTC offer creation stalls', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'auto' });
    await waitFor(() => expect(global.RTCPeerConnection).toHaveBeenCalledTimes(1));
    peers[0].createOffer.mockImplementation(() => new Promise(() => {}));
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    act(() => {
      sockets[0].readyState = global.WebSocket.OPEN;
      void sockets[0].onopen();
    });
    expect(peers[0].createOffer).toHaveBeenCalledTimes(1);

    act(() => {
      jest.advanceTimersByTime(9999);
    });
    expect(global.WebSocket).toHaveBeenCalledTimes(1);

    act(() => {
      jest.advanceTimersByTime(1);
    });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(2));
    expect(sockets[1].url).toContain('/ws/video_feed');
    expect(peers[0].close).toHaveBeenCalledTimes(1);
    expect(sockets[0].close).toHaveBeenCalledTimes(1);
  });

  test('resets the auto fallback deadline when WebRTC signaling progresses', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'auto' });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));
    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      sockets[0].onopen();
    });

    act(() => {
      jest.advanceTimersByTime(11000);
    });
    expect(global.WebSocket).toHaveBeenCalledTimes(1);

    await act(async () => {
      await sockets[0].onmessage({
        data: JSON.stringify({
          type: 'answer',
          payload: { type: 'answer', sdp: 'mock-answer' },
        }),
      });
    });

    act(() => {
      jest.advanceTimersByTime(14999);
    });
    expect(global.WebSocket).toHaveBeenCalledTimes(1);

    act(() => {
      jest.advanceTimersByTime(1);
    });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(2));
    expect(sockets[1].url).toContain('/ws/video_feed');
  });

  test('auto protocol still falls back when a WebRTC track renders no frame', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'auto' });

    await waitFor(() => {
      expect(global.RTCPeerConnection).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      sockets[0].onopen();
      await sockets[0].onmessage({
        data: JSON.stringify({
          type: 'answer',
          payload: { type: 'answer', sdp: 'mock-answer' },
        }),
      });
    });

    act(() => {
      peers[0].ontrack({
        track: { kind: 'video' },
        streams: [{ id: 'mock-stream' }],
      });
      peers[0].iceConnectionState = 'connected';
      peers[0].oniceconnectionstatechange();
    });

    expect(screen.getByTestId('webrtc-video'))
      .toHaveAttribute('data-frame-ready', 'false');

    act(() => {
      jest.advanceTimersByTime(10000);
    });

    await waitFor(() => {
      expect(global.WebSocket).toHaveBeenCalledTimes(2);
    });
    expect(sockets[1].url).toContain('/ws/video_feed');
  });

  test('a decoded WebRTC frame marks the stream ready and cancels auto fallback', async () => {
    jest.useFakeTimers();
    const sockets = installMockWebSocket();
    const peers = installMockPeerConnection();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    renderVideo({ protocol: 'auto' });

    await waitFor(() => {
      expect(global.RTCPeerConnection).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));

    await act(async () => {
      sockets[0].readyState = global.WebSocket.OPEN;
      sockets[0].onopen();
      await sockets[0].onmessage({
        data: JSON.stringify({
          type: 'answer',
          payload: { type: 'answer', sdp: 'mock-answer' },
        }),
      });
    });

    const video = screen.getByTestId('webrtc-video');
    act(() => {
      peers[0].ontrack({
        track: { kind: 'video' },
        streams: [{ id: 'mock-stream' }],
      });
      peers[0].iceConnectionState = 'connected';
      peers[0].oniceconnectionstatechange();
    });
    expect(video).toHaveAttribute('data-frame-ready', 'false');

    fireEvent.loadedData(video);

    expect(video).toHaveAttribute('data-frame-ready', 'true');
    expect(screen.queryByText('Waiting for video frames...')).not.toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(20000);
    });

    expect(global.WebSocket).toHaveBeenCalledTimes(1);
    expect(sockets[0].url).toContain('/ws/webrtc_signaling');
  });
});
