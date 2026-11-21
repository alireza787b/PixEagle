import React from 'react';
import {
  Box, Button, FormControlLabel, InputAdornment, MenuItem, Paper, Stack, Switch,
  TextField, Typography,
} from '@mui/material';
import { Undo } from '@mui/icons-material';
import { parseCommittedNumeric } from '../../utils/numericInput';
import {
  humanizeSchemaKey, isEditableSchemaContract, normalizeSchemaOptions,
} from '../../utils/configEditorSchemaUtils';
import FollowerConfigEditor from './FollowerConfigEditor';
import SafetyLimitsEditor from './SafetyLimitsEditor';
import SmartValueEditor from './SmartValueEditor';

export const touchControls = {
  '& .MuiButton-root, & .MuiIconButton-root, & .MuiSwitch-root': { minHeight: 44, minWidth: 44 },
  '& .MuiInputBase-root': { minHeight: 44 },
};

export function settingLabel(name, schema) {
  return schema?.label || schema?.display_name || humanizeSchemaKey(name.replace(/([a-z])([A-Z])/g, '$1_$2'))
    .replace(/\b(Fps|Osd|Rtsp|Usb|Udp|Tcp|Http|Url)\b/g, (word) => word.toUpperCase());
}

export function matchesSetting(name, definition, query) {
  return [name, settingLabel(name, definition), definition?.description].some(
    (value) => typeof value === 'string' && value.toLowerCase().includes(query)
  ) || Object.entries(definition?.parameters || definition?.properties || {}).some(
    ([key, child]) => matchesSetting(key, child, query)
  );
}

function SettingsField({ label, section, name, definition, definitions, value, values, entry, disabled, onEdit }) {
  const options = normalizeSchemaOptions(definition.options);
  const props = { label, fullWidth: true, size: 'small', disabled };
  const change = (next) => onEdit(next);
  if (!isEditableSchemaContract(definition)) {
    return <TextField {...props} disabled value={typeof value === 'object' ? JSON.stringify(value) : value ?? ''} />;
  }
  if (definition.type === 'boolean') {
    return <FormControlLabel label={value ? 'On' : 'Off'} control={
      <Switch checked={value === true} inputProps={{ 'aria-label': label }}
        disabled={disabled} onChange={(event) => change(event.target.checked)} />
    } />;
  }
  if (options.length && !definition.allow_custom_values) {
    const selected = options.findIndex((option) => option.value === value);
    return <TextField {...props} select value={selected < 0 ? '' : selected}
      onChange={(event) => change(options[Number(event.target.value)].value)}>
      {options.map((option, index) => <MenuItem key={index} value={index}>{option.label}</MenuItem>)}
    </TextField>;
  }
  if (['integer', 'float', 'number'].includes(definition.type)) {
    return <TextField {...props} value={entry?.text ?? value ?? ''}
      error={Boolean(entry?.error)} helperText={entry?.error || (value === null ? definition.null_label : undefined)}
      inputProps={{ inputMode: definition.type === 'integer' ? 'numeric' : 'decimal' }}
      InputProps={definition.unit ? { endAdornment: <InputAdornment position="end">{definition.unit}</InputAdornment> } : undefined}
      onChange={(event) => {
        const text = event.target.value;
        if (definition.nullable && !text.trim()) { onEdit(null, { text }); return; }
        const parsed = parseCommittedNumeric(text, definition.type);
        let error = !parsed.valid ? 'Enter a valid number.' : null;
        if (parsed.valid && definition.min != null && parsed.value < definition.min) error = `Minimum ${definition.min}`;
        if (parsed.valid && definition.max != null && parsed.value > definition.max) error = `Maximum ${definition.max}`;
        onEdit(parsed.value, { text, error });
      }} />;
  }
  if (section === 'Safety' && ['GlobalLimits', 'FollowerOverrides'].includes(name)) {
    return <SafetyLimitsEditor type={name} value={value || {}} schema={definition}
      referenceSchema={definitions.GlobalLimits} globalLimits={values.GlobalLimits}
      disabled={disabled} onChange={change} />;
  }
  if (section === 'Follower' && ['General', 'FollowerOverrides'].includes(name)) {
    return <FollowerConfigEditor type={name} value={value || {}} schema={definition}
      referenceSchema={definitions.General} generalDefaults={values.General}
      disabled={disabled} onChange={change} />;
  }
  if (['object', 'array'].includes(definition.type)) {
    return <SmartValueEditor value={value} schema={definition} mode="inline" disabled={disabled} onChange={change} />;
  }
  return <TextField {...props} value={value ?? ''} onChange={(event) => change(event.target.value)}
    placeholder={definition.allow_custom_values ? options.map((option) => option.label).join(', ') : undefined} />;
}

export default function SectionEditor({ section, schema, saved, draft, onEdit, onUndo, disabled, query, showDefaults, fieldIssue }) {
  const scalar = !schema.parameters;
  const definitions = schema.parameters || { [section]: schema };
  const persisted = scalar ? { [section]: saved } : (saved || {});
  const values = { ...persisted };
  Object.keys(definitions).forEach((name) => {
    const entry = draft[JSON.stringify(scalar ? [section] : [section, name])];
    if (entry && !entry.error) values[name] = entry.value;
  });
  const rows = Object.entries(definitions).filter(([name, definition]) => !query ||
    settingLabel(section, schema).toLowerCase().includes(query) || matchesSetting(name, definition, query));
  return <Stack spacing={1.5} sx={touchControls}>
    <Typography component="h2" variant="h5">{settingLabel(section, schema)}</Typography>
    {rows.map(([name, definition]) => {
      const path = scalar ? [section] : [section, name];
      const entry = draft[JSON.stringify(path)];
      const label = settingLabel(name, definition);
      const value = Object.hasOwn(values, name) ? values[name] : definition.default;
      return <Paper variant="outlined" key={name} sx={{
        px: { xs: 2, md: 2.5 }, py: 1.5, borderColor: entry ? 'primary.main' : 'divider',
      }}>
        <Box sx={{ display: 'grid', gap: 1.5, alignItems: 'center',
          gridTemplateColumns: { xs: '1fr', lg: definition.type === 'object' ? '1fr' : 'minmax(0,1fr) minmax(230px,1fr)' } }}>
          <Box>
            <Typography fontWeight={600}>{label}</Typography>
            {definition.description && <Typography variant="body2" color="text.secondary">{definition.description}</Typography>}
          </Box>
          <SettingsField {...{ label, section, name, definitions, definition, value, values, entry, disabled }}
            onEdit={(next, input) => onEdit(path, next, input)} />
        </Box>
        {fieldIssue && path.every((key, index) => key === fieldIssue.path[index]) && (
          <Typography variant="body2" color="error">{fieldIssue.message}</Typography>
        )}
        <Stack direction="row" flexWrap="wrap" gap={1}>
          {entry && <Button size="small" startIcon={<Undo />} disabled={disabled} onClick={() => onUndo(path)}>Undo edit</Button>}
          {showDefaults && Object.hasOwn(definition, 'default') && JSON.stringify(value) !== JSON.stringify(definition.default)
            && isEditableSchemaContract(definition) && (
              <Button size="small" disabled={disabled} onClick={() => onEdit(path, definition.default)}>Use default</Button>
            )}
        </Stack>
      </Paper>;
    })}
    {!rows.length && <Typography color="text.secondary">No matching settings in this section.</Typography>}
  </Stack>;
}
