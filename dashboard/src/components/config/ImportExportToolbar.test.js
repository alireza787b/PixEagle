import { fireEvent, render, screen } from '@testing-library/react';
import ImportExportToolbar from './ImportExportToolbar';

jest.mock('../../hooks/useResponsive', () => ({
  useResponsive: () => ({ isMobile: true, isTablet: false }),
}));
jest.mock('./ExportDialog', () => () => null);
jest.mock('./ImportDialog', () => () => null);
jest.mock('./BackupHistoryDialog', () => () => null);
jest.mock('./AuditLogDialog', () => () => null);

test('blocks global mutation entry points when the full schema is unavailable', () => {
  render(
    <ImportExportToolbar
      changesCount={1}
      syncAvailableCount={2}
      mutationsAllowed={false}
      mutationBlockReason="Schema unavailable"
    />
  );

  expect(screen.getByRole('button', { name: /sync/i })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: /more configuration actions/i }));
  expect(screen.getByRole('menuitem', { name: /import/i })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('menuitem', { name: /reset to defaults/i })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('menuitem', { name: /export/i })).not.toHaveAttribute('aria-disabled', 'true');
});
