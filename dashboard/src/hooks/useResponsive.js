// dashboard/src/hooks/useResponsive.js
/**
 * useResponsive Hook
 *
 * Centralized responsive breakpoint detection for mobile-first design.
 * Provides consistent breakpoint logic across all components.
 *
 * Breakpoints (MUI defaults):
 * - Mobile: < 600px (xs)
 * - Tablet: 600-900px (sm to md)
 * - Compact Desktop: 900-1200px (md to lg) -- card layout preferred, table too cramped
 * - Desktop: >= 1200px (lg+) -- full table layout
 */

import { useMediaQuery, useTheme } from '@mui/material';

export function useResponsive() {
  const theme = useTheme();

  // Breakpoint detection
  const isMobile = useMediaQuery(theme.breakpoints.down('sm')); // < 600px
  const isTablet = useMediaQuery(theme.breakpoints.between('sm', 'md')); // 600-900px
  const isCompactDesktop = useMediaQuery(theme.breakpoints.between('md', 'lg')); // 900-1200px
  const isDesktop = useMediaQuery(theme.breakpoints.up('md')); // >= 900px

  // Table layout needs >= 1400px for comfortable spacing
  const compactTable = !useMediaQuery(theme.breakpoints.up(1400));

  // Responsive behavior helpers
  return {
    // Primary breakpoint flags
    isMobile,
    isTablet,
    isCompactDesktop,
    isDesktop,

    // Table layout helpers
    compactTable,

    // Slider visibility (hide on phones to save space and improve UX)
    showSliders: !isMobile,

    // Drawer variant for navigation
    sidebarVariant: isMobile ? 'temporary' : 'persistent',

    // Touch target sizing (WCAG AAA: 44px minimum)
    touchTargetSize: isMobile ? 'medium' : 'small',

    // Input field widths
    inputWidth: isMobile ? '100%' : 'auto',

    // Button sizing for touch-friendly interaction
    buttonSize: isMobile ? 'medium' : 'small',

    // Icon button sizing
    iconButtonSize: isMobile ? 'medium' : 'small',

    // Spacing scale (responsive gap/padding)
    spacing: {
      xs: isMobile ? 1 : 2,
      sm: isMobile ? 1.5 : 2,
      md: isMobile ? 2 : 3
    },

    // Dialog configuration
    dialogMaxWidth: isMobile ? 'xs' : 'sm',
    dialogFullScreen: isMobile,

    // Typography variant helpers
    headingVariant: {
      h4: isMobile ? 'h6' : 'h5',
      h5: isMobile ? 'subtitle1' : 'h6',
      h6: isMobile ? 'subtitle2' : 'h6'
    }
  };
}

export default useResponsive;
