import { act, render, screen, waitFor } from '@testing-library/react';
import VideoStream from './VideoStream';
import {
  clearDashboardAuthSession,
  setDashboardAuthSession,
} from '../services/apiClient';

describe('VideoStream browser-session media authorization', () => {
  const originalWebSocket = global.WebSocket;
  const originalRTCPeerConnection = global.RTCPeerConnection;

  beforeEach(() => {
    jest.spyOn(console, 'log').mockImplementation(() => {});
    clearDashboardAuthSession(null);
  });

  afterEach(() => {
    jest.restoreAllMocks();
    global.WebSocket = originalWebSocket;
    global.RTCPeerConnection = originalRTCPeerConnection;
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

  test('blocks websocket video when browser session lacks media read scope', async () => {
    global.WebSocket = jest.fn();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: false,
      principal: { scopes: [] },
    });

    render(<VideoStream protocol="websocket" />);

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

    render(<VideoStream protocol="websocket" />);

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

    render(<VideoStream protocol="websocket" />);

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

  test('blocks webrtc setup when browser session lacks media read scope', async () => {
    global.WebSocket = jest.fn();
    global.RTCPeerConnection = jest.fn();
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['actions:execute'] },
    });

    render(<VideoStream protocol="webrtc" />);

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

    render(<VideoStream protocol="http" src="http://192.168.10.2:5077/video_feed" />);

    expect(await screen.findByText(/Authenticated media session with media:read scope is required/)).toBeInTheDocument();
    expect(screen.queryByAltText('Live Stream')).not.toBeInTheDocument();
  });

  test('uses credentialed HTTP media loading in browser-session mode', () => {
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
    });

    render(<VideoStream protocol="http" src="http://192.168.10.2:5077/video_feed" />);

    expect(screen.getByAltText('Live Stream')).toHaveAttribute('crossorigin', 'use-credentials');
  });
});
