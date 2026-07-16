// Adapts the backend's nested Follower schema for the specialized editor.

import {
  additionalPropertySchema,
  allowsTypedCustomProperties,
  buildFollowerCatalog,
  getSchemaContractIssue,
  groupFollowersByType,
  hasObjectSchemaContract,
  humanizeSchemaKey,
  isPlainObject,
  normalizePropertySchema,
  readOnlyPropertyMetadata,
  schemaDefaults,
  schemaProperties,
} from './configEditorSchemaUtils';
import { FOLLOWER_TYPES } from './safetySchemaUtils';

const propertyCategory = (name) => {
  if (name.includes('RATE') || name.includes('INTERVAL')) return 'timing';
  if (name.includes('SMOOTH')) return 'smoothing';
  if (name.includes('TARGET_LOSS')) return 'target_loss';
  if (name.includes('GUIDANCE') || name.includes('MODE_SWITCH')) return 'guidance';
  if (name.includes('ALTITUDE')) return 'altitude';
  return 'general';
};

const subsectionCategory = (name) => (
  name.includes('YAW') ? 'yaw_smoothing' : 'general'
);

const buildGeneralContract = (schema) => {
  const defaults = schemaDefaults(schema);
  const properties = [];
  const subsections = {};

  Object.entries(schemaProperties(schema)).forEach(([name, propertySchema]) => {
    if (propertySchema.type !== 'object') {
      properties.push(normalizePropertySchema(name, propertySchema, {
        category: propertyCategory(name),
        fallbackDefault: defaults[name],
      }));
      return;
    }

    const subsectionDefaults = schemaDefaults(propertySchema);
    const nestedProperties = Object.entries(schemaProperties(propertySchema)).map(
      ([propertyName, nestedSchema]) => normalizePropertySchema(propertyName, nestedSchema, {
        category: subsectionCategory(name),
        fallbackDefault: subsectionDefaults[propertyName],
      })
    );

    subsections[name] = {
      label: propertySchema.display_name || propertySchema.label || humanizeSchemaKey(name),
      category: subsectionCategory(name),
      properties: nestedProperties,
      defaults: subsectionDefaults,
      statusKey: nestedProperties.some((property) => property.name === 'ENABLED')
        ? 'ENABLED'
        : null,
      additionalProperties: allowsTypedCustomProperties(propertySchema),
    };
  });

  const flatDefaults = Object.fromEntries(
    properties
      .filter((property) => property.default !== undefined)
      .map((property) => [property.name, property.default])
  );

  return { properties, subsections, flatDefaults };
};

const buildReadOnlyContract = (currentValue = {}, reason) => {
  const properties = [];
  const subsections = {};

  Object.entries(isPlainObject(currentValue) ? currentValue : {}).forEach(([name, value]) => {
    if (isPlainObject(value)) {
      const nestedProperties = Object.entries(value).map(([propertyName, propertyValue]) => (
        readOnlyPropertyMetadata(propertyName, propertyValue, reason)
      ));
      subsections[name] = {
        label: humanizeSchemaKey(name),
        category: subsectionCategory(name),
        properties: nestedProperties,
        defaults: {},
        statusKey: nestedProperties.some((property) => property.name === 'ENABLED')
          ? 'ENABLED'
          : null,
        additionalProperties: false,
      };
      return;
    }
    properties.push(readOnlyPropertyMetadata(name, value, reason));
  });

  return { properties, subsections, flatDefaults: {} };
};

/**
 * Build an editor contract only from complete backend metadata. Current values
 * are used solely to build a read-only display when that contract is missing.
 */
export const createFollowerEditorSchema = ({
  type,
  schema,
  referenceSchema,
  currentValue = {},
} = {}) => {
  const isOverrides = type === 'FollowerOverrides';
  const schemaAvailable = hasObjectSchemaContract(schema);
  const referenceAvailable = !isOverrides || hasObjectSchemaContract(referenceSchema);
  const editable = schemaAvailable && referenceAvailable;
  const schemaIssue = schemaAvailable
    ? (referenceAvailable ? null : getSchemaContractIssue(referenceSchema, 'Follower.General'))
    : getSchemaContractIssue(schema, `Follower.${type || 'configuration'}`);

  const referenceContract = isOverrides
    ? (referenceAvailable
      ? buildGeneralContract(referenceSchema)
      : buildReadOnlyContract({}, schemaIssue))
    : null;
  const general = !isOverrides
    ? (schemaAvailable
      ? buildGeneralContract(schema)
      : buildReadOnlyContract(currentValue, schemaIssue))
    : referenceContract;

  const catalog = isOverrides
    ? buildFollowerCatalog(schemaAvailable ? schema : null, currentValue)
    : { declared: [], migrations: [], all: [] };
  const declaredNames = new Set(catalog.declared.map((follower) => follower.name));

  const followerContractFor = (followerName) => {
    if (!isOverrides) return general;
    if (!schemaAvailable || !declaredNames.has(followerName)) {
      return buildReadOnlyContract(currentValue?.[followerName], schemaIssue || 'Follower is not declared by the server schema');
    }
    return buildGeneralContract(schemaProperties(schema)[followerName]);
  };

  const contractFor = (followerName) => (
    isOverrides ? followerContractFor(followerName) : general
  );
  const schemaFor = (followerName) => (
    isOverrides ? schemaProperties(schema)[followerName] : schema
  );

  const getPropertyByName = (name, followerName) => (
    contractFor(followerName).properties.find((property) => property.name === name)
  );

  return {
    source: editable ? 'server' : 'unavailable',
    editable,
    schemaIssue,
    properties: general.properties,
    generalDefaults: general.flatDefaults,
    subsections: general.subsections,
    followers: catalog.all,
    migrationFollowers: catalog.migrations,
    followersByType: groupFollowersByType(catalog.all),
    editableFollowersByType: groupFollowersByType(catalog.declared),
    isFollowerDeclared: (followerName) => declaredNames.has(followerName),
    getProperties: (followerName) => contractFor(followerName).properties,
    getSubsections: (followerName) => contractFor(followerName).subsections,
    getPropertyByName,
    getSubsectionPropertyByName: (subsectionKey, name, followerName) => (
      contractFor(followerName).subsections[subsectionKey]?.properties.find(
        (property) => property.name === name
      )
    ),
    getAddableProperties: (currentProperties, followerName) => {
      if (!editable || (isOverrides && !declaredNames.has(followerName))) return [];
      const existing = new Set(Object.keys(currentProperties || {}));
      return contractFor(followerName).properties.filter(
        (property) => property.editable && !existing.has(property.name)
      );
    },
    allowsCustomProperties: (followerName) => {
      if (!editable || (isOverrides && !declaredNames.has(followerName))) return false;
      return allowsTypedCustomProperties(schemaFor(followerName));
    },
    getCustomPropertyMeta: (followerName) => {
      const customSchema = additionalPropertySchema(schemaFor(followerName));
      return customSchema ? normalizePropertySchema('', customSchema) : null;
    },
  };
};

export { FOLLOWER_TYPES };

export const PROPERTY_CATEGORIES = {
  timing: { label: 'Control Timing', icon: 'Speed', color: 'primary' },
  smoothing: { label: 'Command Smoothing', icon: 'Tune', color: 'info' },
  target_loss: { label: 'Target Loss Detection', icon: 'GpsOff', color: 'error' },
  guidance: { label: 'Guidance Modes', icon: 'Navigation', color: 'warning' },
  altitude: { label: 'Altitude Control', icon: 'Height', color: 'success' },
  yaw_smoothing: { label: 'Yaw Smoothing Pipeline', icon: 'RotateRight', color: 'secondary' },
  general: { label: 'General', icon: 'Tune', color: 'default' },
};

const followerConfigSchemaUtils = {
  PROPERTY_CATEGORIES,
  FOLLOWER_TYPES,
  createFollowerEditorSchema,
};

export default followerConfigSchemaUtils;
