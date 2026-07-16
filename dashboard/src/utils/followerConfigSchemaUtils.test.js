import { createFollowerEditorSchema } from './followerConfigSchemaUtils';

const generalSchema = {
  type: 'object',
  additional_properties: false,
  properties: {
    CONTROL_UPDATE_RATE: {
      type: 'float',
      default: 37,
      min: 7,
      max: 41,
      step: 2,
      unit: 'hz',
    },
    LATERAL_GUIDANCE_MODE: {
      type: 'string',
      default: 'sideslip',
      options: [
        { value: 'coordinated_turn', label: 'Coordinated turn' },
        { value: 'sideslip', label: 'Sideslip' },
      ],
    },
    DYNAMIC_FILTER: {
      type: 'object',
      default: { ENABLED: true, GAIN: 0.4 },
      properties: {
        ENABLED: { type: 'boolean', default: true },
        GAIN: { type: 'float', default: 0.4, min: 0.2, max: 0.8, step: 0.1 },
      },
    },
  },
};

test('uses backend follower defaults, bounds, enums, and nested subsection metadata', () => {
  const contract = createFollowerEditorSchema({
    type: 'General',
    schema: generalSchema,
  });

  expect(contract.source).toBe('server');
  expect(contract.generalDefaults).toEqual({
    CONTROL_UPDATE_RATE: 37,
    LATERAL_GUIDANCE_MODE: 'sideslip',
  });
  expect(contract.getPropertyByName('CONTROL_UPDATE_RATE')).toMatchObject({
    min: 7,
    max: 41,
    step: 2,
    default: 37,
  });
  expect(contract.getPropertyByName('LATERAL_GUIDANCE_MODE').options.map((option) => option.value)).toEqual([
    'coordinated_turn',
    'sideslip',
  ]);
  expect(contract.getPropertyByName('LATERAL_GUIDANCE_MODE').options.map((option) => option.value)).not.toContain('direct');
  expect(contract.getSubsectionPropertyByName('DYNAMIC_FILTER', 'GAIN')).toMatchObject({
    min: 0.2,
    max: 0.8,
    default: 0.4,
  });
});

test('separates declared override followers from read-only migration entries', () => {
  const contract = createFollowerEditorSchema({
    type: 'FollowerOverrides',
    schema: {
      type: 'object',
      properties: {
        SCHEMA_PROFILE: {
          type: 'object',
          description: 'Schema profile',
          additional_properties: false,
          properties: {
            CONTROL_UPDATE_RATE: generalSchema.properties.CONTROL_UPDATE_RATE,
          },
        },
      },
    },
    referenceSchema: generalSchema,
    currentValue: { CURRENT_PROFILE: { CONTROL_UPDATE_RATE: 20 } },
  });

  expect(contract.followers.map((follower) => follower.name)).toEqual([
    'SCHEMA_PROFILE',
    'CURRENT_PROFILE',
  ]);
  expect(contract.isFollowerDeclared('SCHEMA_PROFILE')).toBe(true);
  expect(contract.isFollowerDeclared('CURRENT_PROFILE')).toBe(false);
  expect(contract.migrationFollowers.map((follower) => follower.name)).toEqual(['CURRENT_PROFILE']);
  expect(contract.getPropertyByName('CONTROL_UPDATE_RATE', 'SCHEMA_PROFILE').default).toBe(37);
  expect(contract.getPropertyByName('CONTROL_UPDATE_RATE', 'CURRENT_PROFILE').editable).toBe(false);
});

test('does not replace an empty server contract with the fallback catalog', () => {
  const contract = createFollowerEditorSchema({
    type: 'FollowerOverrides',
    schema: { type: 'object', properties: {} },
    referenceSchema: generalSchema,
  });

  expect(contract.source).toBe('server');
  expect(contract.followers).toEqual([]);
});

test('keeps values visible but refuses edits when the server schema is unavailable', () => {
  const contract = createFollowerEditorSchema({
    type: 'General',
    schema: null,
    currentValue: { LATERAL_GUIDANCE_MODE: 'sideslip' },
  });

  expect(contract.source).toBe('unavailable');
  expect(contract.editable).toBe(false);
  expect(contract.getPropertyByName('LATERAL_GUIDANCE_MODE')).toMatchObject({
    type: 'string',
    editable: false,
  });
  expect(contract.getPropertyByName('LATERAL_GUIDANCE_MODE').options).toBeUndefined();
  expect(contract.getAddableProperties({})).toEqual([]);
  expect(contract.allowsCustomProperties()).toBe(false);
});

test('rejects object defaults as an editable nested contract', () => {
  const contract = createFollowerEditorSchema({
    type: 'General',
    schema: {
      type: 'object',
      properties: {
        YAW_SMOOTHING: {
          type: 'object',
          default: { ENABLED: true },
        },
      },
    },
    currentValue: { YAW_SMOOTHING: { ENABLED: true } },
  });

  expect(contract.editable).toBe(false);
  expect(contract.schemaIssue).toMatch(/properties must explicitly describe/i);
  expect(contract.getSubsectionPropertyByName('YAW_SMOOTHING', 'ENABLED').editable).toBe(false);
});
