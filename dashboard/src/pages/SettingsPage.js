// dashboard/src/pages/SettingsPage.js
import React, { useState, useMemo } from 'react';
import {
  Box, Container, Typography, CircularProgress, Alert, Paper, Divider,
  List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Collapse, TextField, InputAdornment, Chip, IconButton, Tooltip,
  Snackbar
} from '@mui/material';
import {
  Settings, Search, ExpandLess, ExpandMore, Videocam, Router,
  GpsFixed, Navigation, Shield, Tune, AutoFixHigh, Tv,
  Refresh, Warning
} from '@mui/icons-material';

import { useConfigSections, useConfigSection, useConfigSearch, useConfigDiff } from '../hooks/useConfig';
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

  const [selectedSection, setSelectedSection] = useState(null);
  const [expandedCategories, setExpandedCategories] = useState({});
  const [searchQuery, setSearchQuery] = useState('');
  const [pendingRestartParams, setPendingRestartParams] = useState([]);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });

  // Sort categories by order
  const sortedCategories = useMemo(() => {
    return categoryOrder.filter(cat => groupedSections[cat]?.length > 0);
  }, [groupedSections]);

  const toggleCategory = (category) => {
    setExpandedCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }));
  };

  const handleSectionSelect = (section) => {
    setSelectedSection(section);
    clearResults();
    setSearchQuery('');
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
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
          <Box>
            <Typography variant="h4" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
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
      </Box>

      {/* Main Layout */}
      <Box sx={{ display: 'flex', gap: 3 }}>
        {/* Sidebar */}
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
              const catSections = groupedSections[category] || [];
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
                      {catSections.map((section) => (
                        <ListItemButton
                          key={section.name}
                          sx={{ pl: 4 }}
                          selected={selectedSection === section.name}
                          onClick={() => handleSectionSelect(section.name)}
                        >
                          <ListItemText
                            primary={section.display_name}
                            secondary={`${section.parameter_count} params`}
                          />
                        </ListItemButton>
                      ))}
                    </List>
                  </Collapse>
                </React.Fragment>
              );
            })}
          </List>
        </Paper>

        {/* Content Area */}
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          {selectedSection ? (
            <SectionEditor
              sectionName={selectedSection}
              onRebootRequired={handleRebootRequired}
              onMessage={handleSnackbar}
            />
          ) : (
            <Paper sx={{ p: 4, textAlign: 'center' }}>
              <Settings sx={{ fontSize: 80, color: 'text.disabled', mb: 2 }} />
              <Typography variant="h6" color="text.secondary">
                Select a section to edit
              </Typography>
              <Typography variant="body2" color="text.disabled">
                Use the sidebar to navigate through configuration sections,
                or search for specific parameters.
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
