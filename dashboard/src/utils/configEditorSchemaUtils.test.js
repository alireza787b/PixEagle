import {
  buildFollowerCatalog,
  hasObjectSchemaContract,
  isEditableSchemaContract,
  normalizePropertySchema,
  validateFullConfigSchema,
  validateSectionSchema,
} from './configEditorSchemaUtils';

test('requires explicit recursive properties for editable object contracts', () => {
  expect(hasObjectSchemaContract({
    type: 'object',
    default: { ENABLED: true },
  })).toBe(false);

  expect(hasObjectSchemaContract({
    type: 'object',
    properties: {
      ENABLED: { type: 'boolean', default: true },
    },
  })).toBe(true);
});

test('requires an explicit item contract before arrays become editable', () => {
  expect(isEditableSchemaContract({ type: 'array', default: ['one'] })).toBe(false);
  expect(isEditableSchemaContract({ type: 'array', item_type: 'string' })).toBe(true);
});

test('validates the section envelope without promoting incomplete structured parameters', () => {
  const schema = {
    parameters: {
      LEGACY_OBJECT: { type: 'object', default: { value: 1 } },
    },
  };

  expect(validateSectionSchema(schema)).toEqual({ valid: true, error: null });
  expect(isEditableSchemaContract(schema.parameters.LEGACY_OBJECT)).toBe(false);
  expect(validateSectionSchema({ parameters: { BROKEN: {} } }).valid).toBe(false);
});

test('requires every section before enabling global configuration mutations', () => {
  expect(validateFullConfigSchema({
    sections: {
      Streaming: {
        parameters: {
          ENABLE_STREAMING: { type: 'boolean' },
        },
      },
      Tracking: {
        parameters: {
          TRACKER_TYPE: { type: 'string' },
        },
      },
    },
  })).toEqual({ valid: true, error: null });

  expect(validateFullConfigSchema({ sections: {} }).valid).toBe(false);
  expect(validateFullConfigSchema({
    sections: {
      Broken: { parameters: { VALUE: {} } },
    },
  })).toEqual({
    valid: false,
    error: 'Section Broken: Parameter VALUE has a missing or unsupported type',
  });
});

test('keeps closed enums closed unless custom values are explicitly allowed', () => {
  const closed = normalizePropertySchema('MODE', {
    type: 'string',
    options: ['safe', 'hold'],
  });
  const open = normalizePropertySchema('MODE', {
    type: 'string',
    options: ['safe', 'hold'],
    allow_custom_values: true,
  });

  expect(closed.allowCustomValues).toBe(false);
  expect(open.allowCustomValues).toBe(true);
});

test('catalogues undeclared current followers as migration entries', () => {
  const catalog = buildFollowerCatalog({
    type: 'object',
    properties: {
      MC_DECLARED: { type: 'object', properties: {} },
    },
  }, {
    MC_DECLARED: {},
    LEGACY_PROFILE: { LIMIT: 1 },
  });

  expect(catalog.declared.map((entry) => entry.name)).toEqual(['MC_DECLARED']);
  expect(catalog.migrations).toEqual([
    expect.objectContaining({ name: 'LEGACY_PROFILE', readOnly: true, declared: false }),
  ]);
});
