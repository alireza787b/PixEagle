// dashboard/src/hooks/useFollowerSchema.js
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';

const API_URL = `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`;

export const useFollowerSchema = (refreshInterval = 10000) => {
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulSchema = useRef(null);

  const fetchSchema = useCallback(async () => {
    try {
      const response = await axios.get(`${API_URL}/api/follower/schema`);
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulSchema.current)) {
        setSchema(response.data);
        lastSuccessfulSchema.current = response.data;
      }
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching follower schema:', err);
      setError(err.message);
      // Keep previous successful data on error
      if (lastSuccessfulSchema.current) {
        setSchema(lastSuccessfulSchema.current);
      }
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSchema();
    
    const interval = setInterval(fetchSchema, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchSchema, refreshInterval]);

  return useMemo(() => ({ 
    schema, 
    loading, 
    error, 
    refetch: fetchSchema 
  }), [schema, loading, error, fetchSchema]);
};

export const useCurrentFollowerProfile = (refreshInterval = 2000) => {
  const [currentProfile, setCurrentProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const lastSuccessfulProfile = useRef(null);
  const abortControllerRef = useRef(null);

  const fetchCurrentProfile = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    abortControllerRef.current = new AbortController();
    
    try {
      const response = await axios.get(`${API_URL}/api/follower/current-profile`, {
        signal: abortControllerRef.current.signal
      });
      
      // Only update if data actually changed
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulProfile.current)) {
        setCurrentProfile(response.data);
        lastSuccessfulProfile.current = response.data;
      }
      
      setError(null);
      setLoading(false);
      setIsTransitioning(false);
    } catch (err) {
      if (err.name !== 'CanceledError') {
        console.error('Error fetching current follower profile:', err);
        setError(err.message);
        // Keep previous successful data on error
        if (lastSuccessfulProfile.current) {
          setCurrentProfile(lastSuccessfulProfile.current);
        }
        setLoading(false);
      }
    }
  }, []);

  const switchProfile = useCallback(async (profileName) => {
    setIsTransitioning(true);
    try {
      const response = await axios.post(`${API_URL}/api/follower/switch-profile`, {
        profile_name: profileName
      });
      
      if (response.data.status === 'success') {
        // Wait a moment for the backend to update, then refresh
        setTimeout(() => {
          fetchCurrentProfile();
        }, 500);
        return { success: true, message: response.data.message };
      } else {
        setIsTransitioning(false);
        return { success: false, message: response.data.message };
      }
    } catch (err) {
      console.error('Error switching follower profile:', err);
      setIsTransitioning(false);
      return { success: false, message: err.message };
    }
  }, [fetchCurrentProfile]);

  useEffect(() => {
    fetchCurrentProfile();
    
    const interval = setInterval(fetchCurrentProfile, refreshInterval);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchCurrentProfile, refreshInterval]);

  return useMemo(() => ({ 
    currentProfile, 
    loading, 
    error, 
    isTransitioning,
    switchProfile,
    refetch: fetchCurrentProfile 
  }), [currentProfile, loading, error, isTransitioning, switchProfile, fetchCurrentProfile]);
};

export const useFollowerProfiles = (refreshInterval = 5000) => {
  const [profiles, setProfiles] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulProfiles = useRef(null);

  const fetchProfiles = useCallback(async () => {
    try {
      const response = await axios.get(`${API_URL}/api/follower/profiles`);
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulProfiles.current)) {
        setProfiles(response.data);
        lastSuccessfulProfiles.current = response.data;
      }
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching follower profiles:', err);
      setError(err.message);
      if (lastSuccessfulProfiles.current) {
        setProfiles(lastSuccessfulProfiles.current);
      }
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfiles();
    
    const interval = setInterval(fetchProfiles, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchProfiles, refreshInterval]);

  return useMemo(() => ({ 
    profiles, 
    loading, 
    error, 
    refetch: fetchProfiles 
  }), [profiles, loading, error, fetchProfiles]);
};

export const useDynamicFields = (schema, currentProfile) => {
  return useMemo(() => {
    if (!schema || !currentProfile || !currentProfile.active) {
      return { fieldGroups: {}, fieldDisplayOrder: [] };
    }

    // Get available fields for current profile
    const availableFields = currentProfile.available_fields || [];
    
    // Group fields by UI category
    const groups = {};
    const uiConfig = schema.ui_config || {};
    const fieldGroupsConfig = uiConfig.field_groups || {};
    
    // Create groups
    Object.entries(fieldGroupsConfig).forEach(([groupKey, groupConfig]) => {
      const groupFields = groupConfig.fields.filter(field => 
        availableFields.includes(field)
      );
      
      if (groupFields.length > 0) {
        groups[groupKey] = {
          name: groupConfig.name,
          color: groupConfig.color,
          fields: groupFields
        };
      }
    });
    
    // Set display order
    const displayOrder = uiConfig.field_display_order || [];
    const orderedFields = displayOrder.filter(field => 
      availableFields.includes(field)
    );
    
    return { fieldGroups: groups, fieldDisplayOrder: orderedFields };
  }, [schema, currentProfile]);
};