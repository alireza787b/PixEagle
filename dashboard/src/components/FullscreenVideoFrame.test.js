import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import FullscreenVideoFrame from './FullscreenVideoFrame';

const originalFullscreenElement = Object.getOwnPropertyDescriptor(document, 'fullscreenElement');
const originalFullscreenEnabled = Object.getOwnPropertyDescriptor(document, 'fullscreenEnabled');

afterEach(() => {
  if (originalFullscreenElement) {
    Object.defineProperty(document, 'fullscreenElement', originalFullscreenElement);
  } else {
    Reflect.deleteProperty(document, 'fullscreenElement');
  }
  if (originalFullscreenEnabled) {
    Object.defineProperty(document, 'fullscreenEnabled', originalFullscreenEnabled);
  } else {
    Reflect.deleteProperty(document, 'fullscreenEnabled');
  }
});

test('requests fullscreen and exposes fullscreen layout state to its child', async () => {
  Object.defineProperty(document, 'fullscreenEnabled', {
    configurable: true,
    value: true,
  });
  render(
    <FullscreenVideoFrame>
      {({ isFullscreen }) => <span>{isFullscreen ? 'full' : 'inline'}</span>}
    </FullscreenVideoFrame>
  );

  const frame = screen.getByTestId('fullscreen-video-frame');
  frame.requestFullscreen = jest.fn().mockImplementation(async () => {
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: frame,
    });
    document.dispatchEvent(new Event('fullscreenchange'));
  });
  fireEvent(window, new Event('resize'));

  const button = screen.getByRole('button', { name: 'Fullscreen video' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);

  await waitFor(() => expect(frame.requestFullscreen).toHaveBeenCalledTimes(1));
  expect(await screen.findByText('full')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Exit fullscreen video' })).toBeEnabled();
});

test('disables the control when the browser rejects fullscreen', async () => {
  Object.defineProperty(document, 'fullscreenEnabled', {
    configurable: true,
    value: true,
  });
  render(<FullscreenVideoFrame><span>video</span></FullscreenVideoFrame>);

  const frame = screen.getByTestId('fullscreen-video-frame');
  frame.requestFullscreen = jest.fn().mockRejectedValue(new Error('denied'));
  const button = screen.getByRole('button', { name: 'Fullscreen video' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);

  await waitFor(() => expect(button).toBeDisabled());
  expect(frame.requestFullscreen).toHaveBeenCalledTimes(1);
});
