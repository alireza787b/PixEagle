import { render, screen } from '@testing-library/react';
import RecordingQuickControl from './RecordingQuickControl';
import { useRecording } from '../hooks/useRecording';

jest.mock('../hooks/useRecording', () => ({
  useRecording: jest.fn(),
}));

test('shows the unavailable reason and disables recording controls', () => {
  useRecording.mockReturnValue({
    recordingStatus: { state: 'unavailable' },
    storageStatus: {
      free_gb: 0,
      total_gb: 0,
      used_percent: 0,
      warning_level: 'error',
      error: 'ValueError: recording output directory is not writable',
    },
    recordingAvailable: false,
    recordingUnavailableReason: 'ValueError: recording output directory is not writable',
    loading: false,
    error: null,
    startRecording: jest.fn(),
    pauseRecording: jest.fn(),
    resumeRecording: jest.fn(),
    stopRecording: jest.fn(),
  });

  render(<RecordingQuickControl />);

  expect(screen.getByText('ValueError: recording output directory is not writable')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Record/i })).toBeDisabled();
});
