// Shared adapters for configuration contracts returned by the backend.

const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value || {}, key);
const primitiveSchemaTypes = new Set(['boolean', 'string', 'integer', 'float', 'number']);
const supportedSchemaTypes = new Set([...primitiveSchemaTypes, 'array', 'object']);

export const isPlainObject = (value) => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
);

const inferReadOnlyType = (value) => {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'float';
  if (Array.isArray(value)) return 'array';
  if (isPlainObject(value)) return 'object';
  return 'string';
};

export const readOnlySchemaForValue = (value, reason = 'No complete server schema is available') => ({
  type: inferReadOnlyType(value),
  read_only: true,
  read_only_reason: reason,
});

const validateSchemaNode = (schema, path) => {
  if (!isPlainObject(schema)) return `${path} must be an object`;
  if (!supportedSchemaTypes.has(schema.type)) return `${path}.type is missing or unsupported`;

  if (schema.options !== undefined && !Array.isArray(schema.options)) {
    return `${path}.options must be an array`;
  }

  if (schema.type === 'object') {
    if (!isPlainObject(schema.properties)) {
      return `${path}.properties must explicitly describe the object`;
    }
    for (const [name, childSchema] of Object.entries(schema.properties)) {
      const issue = validateSchemaNode(childSchema, `${path}.properties.${name}`);
      if (issue) return issue;
    }
  }

  if (schema.type === 'array') {
    const itemSchema = isPlainObject(schema.items)
      ? schema.items
      : (schema.item_type ? { type: schema.item_type } : null);
    if (!itemSchema) return `${path} must declare items or item_type`;
    const issue = validateSchemaNode(itemSchema, `${path}.items`);
    if (issue) return issue;
  }

  return null;
};

/**
 * Validate only the section envelope. Individual parameters may still be
 * display-only when their recursive contract is incomplete.
 */
export const validateSectionSchema = (schema) => {
  if (!isPlainObject(schema)) return { valid: false, error: 'Section schema must be an object' };
  if (!isPlainObject(schema.parameters)) {
    return { valid: false, error: 'Section schema must contain a parameters object' };
  }
  for (const [name, parameterSchema] of Object.entries(schema.parameters)) {
    if (!isPlainObject(parameterSchema)) {
      return { valid: false, error: `Parameter ${name} must have a schema object` };
    }
    if (!supportedSchemaTypes.has(parameterSchema.type)) {
      return { valid: false, error: `Parameter ${name} has a missing or unsupported type` };
    }
  }
  return { valid: true, error: null };
};

export const validateFullConfigSchema = (schema) => {
  if (!isPlainObject(schema)) {
    return { valid: false, error: 'Configuration schema must be an object' };
  }
  if (!isPlainObject(schema.sections) || Object.keys(schema.sections).length === 0) {
    return { valid: false, error: 'Configuration schema must contain sections' };
  }
  for (const [sectionName, sectionSchema] of Object.entries(schema.sections)) {
    const validation = validateSectionSchema(sectionSchema);
    if (!validation.valid) {
      return {
        valid: false,
        error: `Section ${sectionName}: ${validation.error}`,
      };
    }
  }
  return { valid: true, error: null };
};

export const getSchemaContractIssue = (schema, path = 'schema') => (
  validateSchemaNode(schema, path)
);

export const isEditableSchemaContract = (schema) => (
  !schema?.read_only && getSchemaContractIssue(schema) === null
);

export const hasObjectSchemaContract = (schema) => (
  schema?.type === 'object' && isEditableSchemaContract(schema)
);

export const humanizeSchemaKey = (name) => String(name || '')
  .toLowerCase()
  .split('_')
  .filter(Boolean)
  .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
  .join(' ');

export const normalizeSchemaOptions = (options) => (
  Array.isArray(options)
    ? options
      .map((option) => {
        if (isPlainObject(option)) {
          if (!hasOwn(option, 'value')) return null;
          const normalized = {
            value: option.value,
            label: option.label || String(option.value),
          };
          if (option.description !== undefined) normalized.description = option.description;
          return normalized;
        }
        return { value: option, label: String(option) };
      })
      .filter(Boolean)
    : []
);

export const normalizePropertySchema = (
  name,
  propertySchema = {},
  { category, fallbackDefault } = {}
) => {
  const options = normalizeSchemaOptions(propertySchema.options);
  const rawType = propertySchema.type;
  let type = rawType;
  if (options.length > 0) type = 'enum';
  else if (['integer', 'float', 'number'].includes(rawType)) type = 'number';

  const metadata = {
    name,
    type,
    schemaType: rawType,
    category,
    description: propertySchema.description || `${humanizeSchemaKey(name)} setting`,
    editable: primitiveSchemaTypes.has(rawType) && !propertySchema.read_only,
    readOnlyReason: propertySchema.read_only_reason,
    allowCustomValues: propertySchema.allow_custom_values === true,
  };

  if (hasOwn(propertySchema, 'default')) metadata.default = propertySchema.default;
  else if (fallbackDefault !== undefined) metadata.default = fallbackDefault;
  if (propertySchema.unit !== undefined) metadata.unit = propertySchema.unit;
  if (propertySchema.min !== undefined) metadata.min = propertySchema.min;
  if (propertySchema.max !== undefined) metadata.max = propertySchema.max;
  if (propertySchema.step !== undefined) metadata.step = propertySchema.step;
  if (options.length > 0) metadata.options = options;

  return metadata;
};

export const readOnlyPropertyMetadata = (name, value, reason) => (
  normalizePropertySchema(name, readOnlySchemaForValue(value, reason))
);

export const schemaProperties = (schema) => (
  isPlainObject(schema?.properties) ? schema.properties : {}
);

export const schemaDefaults = (schema) => {
  const defaults = isPlainObject(schema?.default) ? { ...schema.default } : {};
  Object.entries(schemaProperties(schema)).forEach(([name, propertySchema]) => {
    if (!hasOwn(defaults, name) && hasOwn(propertySchema, 'default')) {
      defaults[name] = propertySchema.default;
    }
  });
  return defaults;
};

export const followerTypeForName = (name) => {
  const normalized = String(name || '').toUpperCase();
  if (normalized.startsWith('MC_')) return 'multicopter';
  if (normalized.startsWith('GM_')) return 'gimbal';
  if (normalized.startsWith('FW_')) return 'fixed_wing';
  return 'other';
};

const followerMetadata = (name, followerSchema, migration = false) => ({
  name,
  label: followerSchema?.display_name || followerSchema?.label || humanizeSchemaKey(name),
  description: migration
    ? 'Undeclared current entry; review the configuration migration before editing'
    : (followerSchema?.description || `${humanizeSchemaKey(name)} follower`),
  type: migration ? 'migration' : followerTypeForName(name),
  declared: !migration,
  readOnly: migration,
});

export const buildFollowerCatalog = (schema, currentValue = {}) => {
  const propertySchemas = schemaProperties(schema);
  const declared = Object.entries(propertySchemas).map(([name, followerSchema]) => (
    followerMetadata(name, followerSchema, false)
  ));
  const migrations = isPlainObject(currentValue)
    ? Object.keys(currentValue)
      .filter((name) => !hasOwn(propertySchemas, name))
      .map((name) => followerMetadata(name, null, true))
    : [];

  return { declared, migrations, all: [...declared, ...migrations] };
};

export const groupFollowersByType = (followers) => (
  (followers || []).reduce((groups, follower) => {
    if (!groups[follower.type]) groups[follower.type] = [];
    groups[follower.type].push(follower);
    return groups;
  }, {})
);

export const additionalPropertySchema = (schema) => {
  if (isPlainObject(schema?.additional_properties)) return schema.additional_properties;
  if (isPlainObject(schema?.additional_property_schema)) return schema.additional_property_schema;
  return null;
};

export const allowsTypedCustomProperties = (schema) => {
  const customSchema = additionalPropertySchema(schema);
  return Boolean(customSchema && isEditableSchemaContract(customSchema));
};
