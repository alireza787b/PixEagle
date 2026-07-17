// Adapts the backend's nested Safety schema for the specialized editor.

import {
  additionalPropertySchema,
  allowsTypedCustomProperties,
  buildFollowerCatalog,
  getSchemaContractIssue,
  groupFollowersByType,
  hasObjectSchemaContract,
  isPlainObject,
  normalizePropertySchema,
  readOnlyPropertyMetadata,
  schemaProperties,
} from './configEditorSchemaUtils';

const safetyCategory = (name) => {
  if (name.includes('ALTITUDE')) return 'altitude';
  if (name.includes('VELOCITY')) return 'velocity';
  if (name.endsWith('_RATE')) return 'rates';
  return 'policy';
};

const normalizeProperties = (properties) => Object.entries(properties).map(
  ([name, propertySchema]) => normalizePropertySchema(name, propertySchema, {
    category: safetyCategory(name),
  })
);

const readOnlyProperties = (currentValue, reason) => Object.entries(
  isPlainObject(currentValue) ? currentValue : {}
).map(([name, value]) => readOnlyPropertyMetadata(name, value, reason));

/**
 * Build an editor contract only from complete backend metadata. Current values
 * remain visible but cannot become an inferred editing contract.
 */
export const createSafetyEditorSchema = ({
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
    ? (referenceAvailable ? null : getSchemaContractIssue(referenceSchema, 'Safety.GlobalLimits'))
    : getSchemaContractIssue(schema, `Safety.${type || 'configuration'}`);

  const catalog = isOverrides
    ? buildFollowerCatalog(schemaAvailable ? schema : null, currentValue)
    : { declared: [], migrations: [], all: [] };
  const declaredNames = new Set(catalog.declared.map((follower) => follower.name));

  const propertySchemaFor = (followerName) => {
    if (!isOverrides) return schemaAvailable ? schema : null;
    if (!schemaAvailable || !declaredNames.has(followerName)) return null;
    return schemaProperties(schema)[followerName];
  };

  const propertiesFor = (followerName) => {
    const propertySchema = propertySchemaFor(followerName);
    if (propertySchema) return normalizeProperties(schemaProperties(propertySchema));
    const currentProperties = isOverrides ? currentValue?.[followerName] : currentValue;
    return readOnlyProperties(
      currentProperties,
      schemaIssue || 'Follower is not declared by the server schema'
    );
  };

  const getPropertyByName = (name, followerName) => (
    propertiesFor(followerName).find((property) => property.name === name)
  );

  return {
    source: editable ? 'server' : 'unavailable',
    editable,
    schemaIssue,
    followers: catalog.all,
    migrationFollowers: catalog.migrations,
    followersByType: groupFollowersByType(catalog.all),
    editableFollowersByType: groupFollowersByType(catalog.declared),
    isFollowerDeclared: (followerName) => declaredNames.has(followerName),
    getProperties: propertiesFor,
    getPropertyByName,
    getAddableProperties: (currentProperties, followerName) => {
      if (!editable || (isOverrides && !declaredNames.has(followerName))) return [];
      const existing = new Set(Object.keys(currentProperties || {}));
      return propertiesFor(followerName).filter(
        (property) => property.editable && !existing.has(property.name)
      );
    },
    isRequired: (name, followerName) => (
      propertySchemaFor(followerName)?.required?.includes(name) === true
    ),
    allowsCustomProperties: (followerName) => {
      if (!editable || (isOverrides && !declaredNames.has(followerName))) return false;
      return allowsTypedCustomProperties(propertySchemaFor(followerName));
    },
    getCustomPropertyMeta: (followerName) => {
      const customSchema = additionalPropertySchema(propertySchemaFor(followerName));
      return customSchema ? normalizePropertySchema('', customSchema) : null;
    },
  };
};

export const PROPERTY_CATEGORIES = {
  altitude: { label: 'Altitude Limits', icon: 'Height', color: 'success' },
  velocity: { label: 'Velocity Limits', icon: 'Speed', color: 'primary' },
  rates: { label: 'Rate Limits', icon: 'RotateRight', color: 'warning' },
  policy: { label: 'Safety Policy', icon: 'Shield', color: 'error' },
};

export const FOLLOWER_TYPES = {
  multicopter: { label: 'Multicopter', icon: 'FlightTakeoff', color: 'primary' },
  gimbal: { label: 'Gimbal', icon: 'CameraAlt', color: 'info' },
  fixed_wing: { label: 'Fixed-Wing', icon: 'Flight', color: 'warning' },
  other: { label: 'Other', icon: 'Tune', color: 'default' },
  migration: { label: 'Needs Migration', icon: 'Warning', color: 'warning' },
};

const safetySchemaUtils = {
  PROPERTY_CATEGORIES,
  FOLLOWER_TYPES,
  createSafetyEditorSchema,
};

export default safetySchemaUtils;
