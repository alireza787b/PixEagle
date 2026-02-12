// dashboard/src/pages/SettingsPage.js
import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import {
  Box, Container, Typography, CircularProgress, Alert, Paper, Divider,
  List, ListItemButton, ListItemIcon, ListItemText,
  Collapse, TextField, InputAdornment, Chip, Tooltip,
  Snackbar, Drawer, Fab, Switch, FormControlLabel, Button, IconButton
} from '@mui/material';
import {
  Settings, Search, ExpandLess, ExpandMore, Videocam, Router,
  GpsFixed, Navigation, Shield, Tune, AutoFixHigh, Tv,
  Menu as MenuIcon, FlightTakeoff, Visibility, VisibilityOff, Save, Close
} from '@mui/icons-material';

import { useConfigSections, useConfigSearch, useConfigDiff, useCurrentFollowerMode, useRelevantSections } from '../hooks/useConfig';
import { useResponsive } from '../hooks/useResponsive';
import { ConfigGlobalStateProvider, useConfigGlobalState } from '../hooks/useConfigGlobalState';
import { useDefaultsSync } from '../hooks/useDefaultsSync';
import SectionEditor from '../components/config/SectionEditor';
import RestartPrompt from '../components/config/RestartPrompt';
import ImportExportToolbar from '../components/config/ImportExportToolbar';
import ConfigStatusBanner from '../components/config/ConfigStatusBanner';
import ChangesDrawer from '../components/config/ChangesDrawer';
import SyncWithDefaultsDialog from '../components/config/SyncWithDefaultsDialog';
import { endpoints } from '../services/apiEndpoints';

// Icon mapping for categories
const categoryIcons = {
  video: <Videocam />,
  network: <Router />,
  tracking: <GpsFixed />,
  detection: <Search />,
  follower: <Navigation />,
  safety: <Shield />,
  control: <Tune />,
  processing: <AutoFixHigh />,
  display: <Tv />,
  other: <Settings />
};

// Category order for display
const categoryOrder = ['video', 'network', 'tracking', 'detection', 'follower', 'safety', 'control', 'processing', 'display', 'other'];

// Inner component that uses global state
const SettingsPageContent = () => {
  const { sections, categories, groupedSections, loading: sectionsLoading, error: sectionsError, refetch } = useConfigSections();
  const { results: searchResults, loading: searchLoading, search, clearResults } = useConfigSearch();
  const { diff, refetch: refetchDiff } = useConfigDiff();
  const { isMobile, isTablet, isDesktop } = useResponsive();
  // Global state available for ConfigStatusBanner
  useConfigGlobalState();

  // Mode-aware filtering (v5.0.0+)
  const { mode: currentMode, modeUpper, isActive: followerActive } = useCurrentFollowerMode();
  const { activeSections, modeSpecificSections } = useRelevantSections(currentMode);

  const [selectedSection, setSelectedSection] = useState(null);
  const [expandedCategories, setExpandedCategories] = useState({});
  const [searchQuery, setSearchQuery] = useState('');
  const [pendingRestartParams, setPendingRestartParams] = useState([]);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info', persistent: false });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [showAllSections, setShowAllSections] = useState(false);
  const [changesDrawerOpen, setChangesDrawerOpen] = useState(false);
  const [syncDialogOpen, setSyncDialogOpen] = useState(false);
  const [autoSaveEnabled, setAutoSaveEnabled] = useState(true);
  const [videoHealth, setVideoHealth] = useState(null);
  const [reconnectingVideo, setReconnectingVideo] = useState(false);
  const [highlightParam, setHighlightParam] = useState(null);
  const [searchActiveIndex, setSearchActiveIndex] = useState(-1);
  const searchResultsRef = useRef(null);
  const searchInputRef = useRef(null);

  // Sync with defaults tracking (v5.4.1+)
  const { counts: syncCounts, refresh: refreshSyncCounts } = useDefaultsSync();

  // Ref for hash navigation processed flag
  const hashProcessedRef = useRef(false);

  // Hash navigation support - handle URL hash to select section (e.g., /settings#Safety)
  useEffect(() => {
    // Only process once when sections are loaded
    if (hashProcessedRef.current || !sections || sections.length === 0) return;

    const hash = window.location.hash.slice(1); // Remove #
    if (!hash) return;

    // Find section by name (case-insensitive)
    const sectionName = sections.find(
      s => s.name.toLowerCase() === hash.toLowerCase()
    )?.name;

    if (sectionName) {
      hashProcessedRef.current = true;

      // Select the section
      setSelectedSection(sectionName);

      // Show all sections to ensure the target is visible
      setShowAllSections(true);

      // Expand the category containing this section
      const sectionMeta = sections.find(s => s.name === sectionName);
      if (sectionMeta?.category) {
        setExpandedCategories(prev => ({ ...prev, [sectionMeta.category]: true }));
      }

      // Clear the hash after navigation to keep URL clean
      if (window.history.replaceState) {
        window.history.replaceState(null, '', window.location.pathname);
      }
    }
  }, [sections]);

  // Close search dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (
        searchResultsRef.current && !searchResultsRef.current.contains(e.target) &&
        searchInputRef.current && !searchInputRef.current.contains(e.target)
      ) {
        clearResults();
        setSearchActiveIndex(-1);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [clearResults]);

  // Filter sections based on mode if not showing all
  const filteredGroupedSections = useMemo(() => {
    if (showAllSections || activeSections.length === 0) {
      return groupedSections;
    }

    // Filter each category to only include active sections
    const filtered = {};
    for (const [category, catSections] of Object.entries(groupedSections)) {
      const relevantSections = catSections.filter(s => activeSections.includes(s.name));
      if (relevantSections.length > 0) {
        filtered[category] = relevantSections;
      }
    }
    return filtered;
  }, [groupedSections, activeSections, showAllSections]);

  // Sort categories by order
  const sortedCategories = useMemo(() => {
    return categoryOrder.filter(cat => filteredGroupedSections[cat]?.length > 0);
  }, [filteredGroupedSections]);

  const toggleCategory = (category) => {
    setExpandedCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }));
  };

  const handleDrawerToggle = () => {
    setDrawerOpen(!drawerOpen);
  };

  const handleSectionSelect = (section) => {
    setSelectedSection(section);
    setHighlightParam(null);
    clearResults();
    setSearchQuery('');
    // Close drawer on mobile after selection
    if (isMobile) {
      setDrawerOpen(false);
    }
  };

  const handleSearch = (e) => {
    const query = e.target.value;
    setSearchQuery(query);
    setSearchActiveIndex(-1);
    if (query.length >= 2) {
      search(query);
    } else {
      clearResults();
    }
  };

  const handleSearchClear = useCallback(() => {
    setSearchQuery('');
    setSearchActiveIndex(-1);
    clearResults();
  }, [clearResults]);

  const handleSearchResultClick = useCallback((result) => {
    // 1. Select the section
    setSelectedSection(result.section);

    // 2. Ensure section is visible even if filtered out by mode-relevance
    setShowAllSections(true);

    // 3. Expand the parent category so the section appears in the sidebar
    const sectionMeta = sections.find(s => s.name === result.section);
    if (sectionMeta?.category) {
      setExpandedCategories(prev => ({ ...prev, [sectionMeta.category]: true }));
    }

    // 4. Set the parameter to highlight in SectionEditor
    setHighlightParam(result.parameter);

    // 5. Clear search state
    clearResults();
    setSearchQuery('');
    setSearchActiveIndex(-1);

    // 6. Close drawer on mobile after selection
    if (isMobile) {
      setDrawerOpen(false);
    }

    // 7. Scroll sidebar to the selected section item after render
    setTimeout(() => {
      const sidebarItem = document.querySelector(
        `[data-section="${result.section}"]`
      );
      if (sidebarItem) {
        sidebarItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }, 150);
  }, [sections, clearResults, isMobile]);

  const handleSearchKeyDown = useCallback((e) => {
    const visibleResults = searchResults.slice(0, 10);
    if (visibleResults.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSearchActiveIndex(prev =>
        prev < visibleResults.length - 1 ? prev + 1 : 0
      );
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSearchActiveIndex(prev =>
        prev > 0 ? prev - 1 : visibleResults.length - 1
      );
    } else if (e.key === 'Enter' && searchActiveIndex >= 0) {
      e.preventDefault();
      handleSearchResultClick(visibleResults[searchActiveIndex]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleSearchClear();
    }
  }, [searchResults, searchActiveIndex, handleSearchResultClick, handleSearchClear]);

  const handleRebootRequired = (section, param) => {
    setPendingRestartParams(prev => {
      const exists = prev.some(p => p.section === section && p.param === param);
      if (!exists) {
        return [...prev, { section, param }];
      }
      return prev;
    });
  };

  // Enhanced snackbar handler with persistent option for safety params
  const handleSnackbar = useCallback((message, severity = 'info', options = {}) => {
    const { persistent = false } = options;
    setSnackbar({ open: true, message, severity, persistent });
  }, []);

  const handleRefreshAll = () => {
    refetch();
    refetchDiff();
  };

  useEffect(() => {
    let mounted = true;

    const loadVideoHealth = async () => {
      try {
        const response = await fetch(endpoints.videoHealth);
        const data = await response.json();
        if (mounted && data?.video) {
          setVideoHealth(data.video);
        }
      } catch (error) {
        if (mounted) {
          setVideoHealth({ status: 'unavailable' });
        }
      }
    };

    loadVideoHealth();
    const interval = setInterval(loadVideoHealth, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleReconnectVideo = useCallback(async () => {
    setReconnectingVideo(true);
    try {
      const response = await fetch(endpoints.videoReconnect, { method: 'POST' });
      const data = await response.json();
      if (data?.video) {
        setVideoHealth(data.video);
      }
      handleSnackbar(data?.message || 'Reconnect request completed', response.ok ? 'success' : 'warning');
    } catch (error) {
      handleSnackbar(`Reconnect failed: ${error.message}`, 'error');
    } finally {
      setReconnectingVideo(false);
    }
  }, [handleSnackbar]);

  const handleConfigImported = () => {
    // Refresh diff after import
    refetchDiff();
    // If a section is selected, it will auto-refresh
  };

  if (sectionsLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (sectionsError) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Alert severity="error">
          Error loading configuration: {sectionsError}
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 2 }}>
      {/* Restart Prompt */}
      {pendingRestartParams.length > 0 && (
        <RestartPrompt
          params={pendingRestartParams}
          onDismiss={() => setPendingRestartParams([])}
          onRestarted={() => {
            // Clear pending params and refresh after restart
            setPendingRestartParams([]);
            handleRefreshAll();
            handleSnackbar('Backend restarted successfully. Configuration applied.', 'success');
          }}
        />
      )}

      {/* Save Status Banner (v5.4.0+) */}
      <Box sx={{ mb: 2 }}>
        <ConfigStatusBanner
          compact={isMobile}
          onViewChanges={() => setChangesDrawerOpen(true)}
        />
      </Box>

      {videoHealth && videoHealth.status !== 'healthy' && (
        <Alert
          severity={videoHealth.status === 'recovering' ? 'info' : 'warning'}
          sx={{ mb: 2 }}
          action={(
            <Button
              color="inherit"
              size="small"
              onClick={handleReconnectVideo}
              disabled={reconnectingVideo}
            >
              {reconnectingVideo ? 'Reconnecting...' : 'Reconnect Camera'}
            </Button>
          )}
        >
          Camera is currently {videoHealth.status}. Settings remain available; fix source config and reconnect.
        </Alert>
      )}

      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', sm: 'flex-start' },
          gap: 2
        }}>
          <Box>
            <Typography
              variant={{ xs: 'h6', md: 'h4' }}
              gutterBottom
              sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
            >
              <Settings /> Configuration Manager
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Manage all PixEagle settings. Changes are saved immediately.
            </Typography>
          </Box>
          <ImportExportToolbar
            changesCount={diff?.length || 0}
            syncAvailableCount={syncCounts?.total || 0}
            onRefresh={handleRefreshAll}
            onMessage={handleSnackbar}
            onConfigImported={handleConfigImported}
            onViewChanges={() => setChangesDrawerOpen(true)}
            onSyncDefaults={() => setSyncDialogOpen(true)}
          />
        </Box>

        {/* Mode Indicator and Section Filter Toggle (v5.0.0+) */}
        <Box sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          alignItems: { xs: 'stretch', sm: 'center' },
          gap: 2,
          mt: 2,
          p: 1.5,
          bgcolor: 'background.paper',
          borderRadius: 1,
          border: 1,
          borderColor: 'divider'
        }}>
          {/* Current Mode Indicator */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexGrow: 1 }}>
            <FlightTakeoff color={followerActive ? 'success' : 'action'} />
            <Box>
              <Typography variant="body2" color="text.secondary">
                Active Mode
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="subtitle2" fontWeight="bold">
                  {modeUpper || 'Loading...'}
                </Typography>
                {followerActive && (
                  <Chip size="small" label="Active" color="success" sx={{ height: 20, fontSize: '0.7rem' }} />
                )}
              </Box>
            </Box>
          </Box>

          {/* Auto-Save Toggle (v5.4.1+) */}
          <Tooltip title={autoSaveEnabled ? 'Changes save automatically on blur/enter' : 'Manual save mode - click Save to persist changes'}>
            <FormControlLabel
              control={
                <Switch
                  checked={autoSaveEnabled}
                  onChange={(e) => setAutoSaveEnabled(e.target.checked)}
                  size="small"
                  color="success"
                />
              }
              label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Save fontSize="small" color={autoSaveEnabled ? 'success' : 'action'} />
                  <Typography variant="body2">
                    {autoSaveEnabled ? 'Auto-Save' : 'Manual'}
                  </Typography>
                </Box>
              }
              sx={{ m: 0 }}
            />
          </Tooltip>

          <Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', sm: 'block' } }} />

          {/* Show All Sections Toggle */}
          <FormControlLabel
            control={
              <Switch
                checked={showAllSections}
                onChange={(e) => setShowAllSections(e.target.checked)}
                size="small"
              />
            }
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                {showAllSections ? <Visibility fontSize="small" /> : <VisibilityOff fontSize="small" />}
                <Typography variant="body2">
                  {showAllSections ? 'All Sections' : 'Mode-Relevant Only'}
                </Typography>
              </Box>
            }
            sx={{ m: 0 }}
          />

          {/* Section Count */}
          {!showAllSections && activeSections.length > 0 && (
            <Chip
              size="small"
              label={`${sortedCategories.reduce((sum, cat) => sum + (filteredGroupedSections[cat]?.length || 0), 0)} sections`}
              color="primary"
              variant="outlined"
            />
          )}
        </Box>
      </Box>

      {/* Hamburger Menu Button (Mobile Only) */}
      {isMobile && (
        <Fab
          color="primary"
          aria-label="menu"
          onClick={handleDrawerToggle}
          sx={{
            position: 'fixed',
            bottom: 16,
            right: 16,
            zIndex: 1200
          }}
        >
          <MenuIcon />
        </Fab>
      )}

      {/* Main Layout */}
      <Box sx={{ display: 'flex', gap: { xs: 0, md: 3 }, position: 'relative' }}>
        {/* Sidebar Content (Shared between Drawer and Paper) */}
        {(() => {
          const sidebarContent = (
            <Box sx={{ width: { xs: 280, sm: 300 }, height: '100%' }}>
              {/* Search */}
              <Box sx={{ p: 2, position: 'sticky', top: 0, bgcolor: 'background.paper', zIndex: 2 }}>
                <TextField
                  inputRef={searchInputRef}
                  fullWidth
                  size="small"
                  placeholder="Search parameters..."
                  value={searchQuery}
                  onChange={handleSearch}
                  onKeyDown={handleSearchKeyDown}
                  role="combobox"
                  aria-expanded={searchResults.length > 0 || searchLoading}
                  aria-controls="search-results-listbox"
                  aria-activedescendant={
                    searchActiveIndex >= 0 ? `search-result-${searchActiveIndex}` : undefined
                  }
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        {searchLoading ? (
                          <CircularProgress size={20} />
                        ) : (
                          <Search />
                        )}
                      </InputAdornment>
                    ),
                    endAdornment: searchQuery ? (
                      <InputAdornment position="end">
                        <IconButton
                          size="small"
                          onClick={handleSearchClear}
                          aria-label="Clear search"
                          edge="end"
                        >
                          <Close fontSize="small" />
                        </IconButton>
                      </InputAdornment>
                    ) : null
                  }}
                />

                {/* Search Results Dropdown */}
                {(searchResults.length > 0 || (searchQuery.length >= 2 && !searchLoading)) && (
                  <Paper
                    elevation={8}
                    ref={searchResultsRef}
                    sx={{
                      mt: 1,
                      maxHeight: 300,
                      overflow: 'auto',
                      position: 'absolute',
                      left: 16,
                      right: 16,
                      zIndex: 1300
                    }}
                  >
                    {searchResults.length > 0 ? (
                      <List
                        dense
                        id="search-results-listbox"
                        role="listbox"
                        aria-label="Search results"
                      >
                        {searchResults.slice(0, 10).map((result, idx) => (
                          <ListItemButton
                            key={`${result.section}-${result.parameter}`}
                            id={`search-result-${idx}`}
                            role="option"
                            aria-selected={idx === searchActiveIndex}
                            selected={idx === searchActiveIndex}
                            onClick={() => handleSearchResultClick(result)}
                          >
                            <ListItemText
                              primary={
                                <Typography
                                  variant="body2"
                                  sx={{ fontFamily: 'monospace', fontWeight: 500 }}
                                >
                                  {result.parameter}
                                </Typography>
                              }
                              secondary={
                                <Typography variant="caption" color="text.secondary" noWrap>
                                  {result.section}
                                  {result.description ? ` \u2014 ${result.description.slice(0, 50)}` : ''}
                                </Typography>
                              }
                            />
                          </ListItemButton>
                        ))}
                      </List>
                    ) : (
                      <Box sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="body2" color="text.secondary">
                          No parameters found for &ldquo;{searchQuery}&rdquo;
                        </Typography>
                      </Box>
                    )}
                  </Paper>
                )}
              </Box>

              <Divider />

              {/* Section List */}
              <List dense>
                {sortedCategories.map((category) => {
                  const catSections = filteredGroupedSections[category] || [];
                  const catInfo = categories[category] || { display_name: category };
                  const isExpanded = expandedCategories[category] === true; // Default collapsed

                  return (
                    <React.Fragment key={category}>
                      <ListItemButton onClick={() => toggleCategory(category)}>
                        <ListItemIcon>
                          {categoryIcons[category] || <Settings />}
                        </ListItemIcon>
                        <ListItemText
                          primary={catInfo.display_name || category}
                          secondary={`${catSections.length} sections`}
                        />
                        {isExpanded ? <ExpandLess /> : <ExpandMore />}
                      </ListItemButton>

                      <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                        <List component="div" disablePadding dense>
                          {catSections.map((section) => {
                            const isModeSpecific = modeSpecificSections.includes(section.name);
                            return (
                              <ListItemButton
                                key={section.name}
                                data-section={section.name}
                                sx={{ pl: 4 }}
                                selected={selectedSection === section.name}
                                onClick={() => handleSectionSelect(section.name)}
                              >
                                <ListItemText
                                  primary={
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                      {section.display_name}
                                      {isModeSpecific && !showAllSections && (
                                        <Chip
                                          size="small"
                                          label="Mode"
                                          color="primary"
                                          sx={{ height: 16, fontSize: '0.6rem', ml: 0.5 }}
                                        />
                                      )}
                                    </Box>
                                  }
                                  secondary={`${section.parameter_count} params`}
                                />
                              </ListItemButton>
                            );
                          })}
                        </List>
                      </Collapse>
                    </React.Fragment>
                  );
                })}
              </List>
            </Box>
          );

          return (
            <>
              {/* Mobile: Temporary Drawer */}
              {isMobile && (
                <Drawer
                  variant="temporary"
                  open={drawerOpen}
                  onClose={handleDrawerToggle}
                  ModalProps={{ keepMounted: true }}
                  sx={{
                    '& .MuiDrawer-paper': {
                      boxSizing: 'border-box',
                      width: 280
                    }
                  }}
                >
                  {sidebarContent}
                </Drawer>
              )}

              {/* Tablet: Persistent Drawer */}
              {isTablet && (
                <Drawer
                  variant="persistent"
                  open={true}
                  sx={{
                    width: 300,
                    flexShrink: 0,
                    '& .MuiDrawer-paper': {
                      width: 300,
                      boxSizing: 'border-box',
                      position: 'relative'
                    }
                  }}
                >
                  {sidebarContent}
                </Drawer>
              )}

              {/* Desktop: Fixed Paper Sidebar */}
              {isDesktop && (
                <Paper
                  sx={{
                    width: 300,
                    flexShrink: 0,
                    maxHeight: 'calc(100vh - 200px)',
                    overflow: 'auto',
                    position: 'sticky',
                    top: 80
                  }}
                >
                  {sidebarContent}
                </Paper>
              )}
            </>
          );
        })()}

        {/* Content Area */}
        <Box sx={{ flexGrow: 1, minWidth: 0, width: '100%' }}>
          {selectedSection ? (
            <SectionEditor
              sectionName={selectedSection}
              highlightParam={highlightParam}
              onHighlightComplete={() => setHighlightParam(null)}
              onRebootRequired={handleRebootRequired}
              onMessage={handleSnackbar}
              autoSaveEnabled={autoSaveEnabled}
            />
          ) : (
            <Paper sx={{ p: { xs: 2, md: 4 }, textAlign: 'center' }}>
              <Settings sx={{ fontSize: { xs: 60, md: 80 }, color: 'text.disabled', mb: 2 }} />
              <Typography variant="h6" color="text.secondary">
                Select a section to edit
              </Typography>
              <Typography variant="body2" color="text.disabled">
                {isMobile
                  ? 'Tap the menu button to browse sections'
                  : 'Use the sidebar to navigate through configuration sections, or search for specific parameters.'
                }
              </Typography>
            </Paper>
          )}
        </Box>
      </Box>

      {/* Changes Drawer (v5.4.1+) */}
      <ChangesDrawer
        open={changesDrawerOpen}
        onClose={() => setChangesDrawerOpen(false)}
        pendingRestartParams={pendingRestartParams}
        onMessage={handleSnackbar}
      />

      {/* Sync With Defaults Dialog (v5.4.1+) */}
      <SyncWithDefaultsDialog
        open={syncDialogOpen}
        onClose={() => {
          setSyncDialogOpen(false);
          // Refresh counts after sync actions
          refreshSyncCounts();
          refetchDiff();
        }}
        onMessage={handleSnackbar}
      />

      {/* Snackbar - Enhanced with 6s duration, persistent for safety params */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={snackbar.persistent ? null : 6000}
        onClose={(event, reason) => {
          // Don't close on clickaway for persistent toasts
          if (snackbar.persistent && reason === 'clickaway') return;
          setSnackbar(prev => ({ ...prev, open: false }));
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity={snackbar.severity}
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
          sx={{
            width: '100%',
            ...(snackbar.persistent && {
              border: 2,
              borderColor: snackbar.severity === 'success' ? 'success.main' : 'warning.main',
            }),
          }}
          variant={snackbar.persistent ? 'filled' : 'standard'}
        >
          {snackbar.message}
          {snackbar.persistent && (
            <Typography variant="caption" display="block" sx={{ mt: 0.5, opacity: 0.9 }}>
              Click X to dismiss
            </Typography>
          )}
        </Alert>
      </Snackbar>
    </Container>
  );
};

// Main component with provider wrapper
const SettingsPage = () => {
  return (
    <ConfigGlobalStateProvider>
      <SettingsPageContent />
    </ConfigGlobalStateProvider>
  );
};

export default SettingsPage;
