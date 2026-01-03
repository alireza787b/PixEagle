// dashboard/src/pages/SettingsPage.js
import React, { useState, useMemo } from 'react';
import {
  Box, Container, Typography, CircularProgress, Alert, Paper, Divider,
  List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Collapse, TextField, InputAdornment, Chip, IconButton, Tooltip,
  Snackbar, Drawer, Fab, Switch, FormControlLabel, Badge
} from '@mui/material';
import {
  Settings, Search, ExpandLess, ExpandMore, Videocam, Router,
  GpsFixed, Navigation, Shield, Tune, AutoFixHigh, Tv,
  Refresh, Warning, Menu as MenuIcon, FlightTakeoff, Visibility, VisibilityOff
} from '@mui/icons-material';

import { useConfigSections, useConfigSection, useConfigSearch, useConfigDiff, useCurrentFollowerMode, useRelevantSections } from '../hooks/useConfig';
import { useResponsive } from '../hooks/useResponsive';
import SectionEditor from '../components/config/SectionEditor';
import RestartPrompt from '../components/config/RestartPrompt';
import ImportExportToolbar from '../components/config/ImportExportToolbar';

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

const SettingsPage = () => {
  const { sections, categories, groupedSections, loading: sectionsLoading, error: sectionsError, refetch } = useConfigSections();
  const { results: searchResults, search, clearResults } = useConfigSearch();
  const { diff, refetch: refetchDiff } = useConfigDiff();
  const { isMobile, isTablet, isDesktop } = useResponsive();

  // Mode-aware filtering (v5.0.0+)
  const { mode: currentMode, modeUpper, isActive: followerActive, loading: modeLoading } = useCurrentFollowerMode();
  const { activeSections, otherSections, modeSpecificSections } = useRelevantSections(currentMode);

  const [selectedSection, setSelectedSection] = useState(null);
  const [expandedCategories, setExpandedCategories] = useState({});
  const [searchQuery, setSearchQuery] = useState('');
  const [pendingRestartParams, setPendingRestartParams] = useState([]);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [showAllSections, setShowAllSections] = useState(false);

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
    if (query.length >= 2) {
      search(query);
    } else {
      clearResults();
    }
  };

  const handleSearchResultClick = (result) => {
    setSelectedSection(result.section);
    clearResults();
    setSearchQuery('');
  };

  const handleRebootRequired = (section, param) => {
    setPendingRestartParams(prev => {
      const exists = prev.some(p => p.section === section && p.param === param);
      if (!exists) {
        return [...prev, { section, param }];
      }
      return prev;
    });
  };

  const handleSnackbar = (message, severity = 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  const handleRefreshAll = () => {
    refetch();
    refetchDiff();
  };

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
            onRefresh={handleRefreshAll}
            onMessage={handleSnackbar}
            onConfigImported={handleConfigImported}
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
              <Box sx={{ p: 2, position: 'sticky', top: 0, bgcolor: 'background.paper', zIndex: 1 }}>
                <TextField
                  fullWidth
                  size="small"
                  placeholder="Search parameters..."
                  value={searchQuery}
                  onChange={handleSearch}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Search />
                      </InputAdornment>
                    )
                  }}
                />

                {/* Search Results */}
                {searchResults.length > 0 && (
                  <Paper elevation={3} sx={{ mt: 1, maxHeight: 300, overflow: 'auto' }}>
                    <List dense>
                      {searchResults.slice(0, 10).map((result, idx) => (
                        <ListItemButton
                          key={idx}
                          onClick={() => handleSearchResultClick(result)}
                        >
                          <ListItemText
                            primary={result.parameter}
                            secondary={`${result.section} - ${result.description?.slice(0, 50)}...`}
                          />
                        </ListItemButton>
                      ))}
                    </List>
                  </Paper>
                )}
              </Box>

              <Divider />

              {/* Section List */}
              <List dense>
                {sortedCategories.map((category) => {
                  const catSections = filteredGroupedSections[category] || [];
                  const catInfo = categories[category] || { display_name: category };
                  const isExpanded = expandedCategories[category] !== false; // Default expanded

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
              onRebootRequired={handleRebootRequired}
              onMessage={handleSnackbar}
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

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
      >
        <Alert severity={snackbar.severity} onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default SettingsPage;
