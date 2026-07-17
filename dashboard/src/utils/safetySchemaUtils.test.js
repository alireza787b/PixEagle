import { createSafetyEditorSchema } from './safetySchemaUtils';

const globalSchema = {
  type: 'object',
  required: ['MAX_VELOCITY'],
  additional_properties: false,
  properties: {
    MAX_VELOCITY: {
      type: 'float',
      default: 2.5,
      min: 0.25,
      max: 7.5,
      step: 0.25,
      unit: 'm/s',
      description: 'Contract velocity limit',
    },
    TARGET_LOSS_ACTION: {
      type: 'string',
      default: 'stop',
      options: [
        { value: 'stop', label: 'Stop now' },
        { value: 'rtl', label: 'Return home' },
      ],
    },
  },
};

test('uses backend safety bounds, defaults, enums, and required fields', () => {
  const contract = createSafetyEditorSchema({
    type: 'GlobalLimits',
    schema: globalSchema,
  });

  expect(contract.source).toBe('server');
  expect(contract.getPropertyByName('MAX_VELOCITY')).toMatchObject({
    default: 2.5,
    min: 0.25,
    max: 7.5,
    step: 0.25,
    unit: 'm/s',
  });
  expect(contract.getPropertyByName('TARGET_LOSS_ACTION').options).toEqual([
    { value: 'stop', label: 'Stop now' },
    { value: 'rtl', label: 'Return home' },
  ]);
  expect(contract.isRequired('MAX_VELOCITY')).toBe(true);
  expect(contract.allowsCustomProperties()).toBe(false);
});

test('separates declared followers from read-only current migration entries', () => {
  const overrideSchema = {
    type: 'object',
    additional_properties: false,
    properties: {
      TEST_PROFILE: {
        type: 'object',
        description: 'Backend test profile',
        additional_properties: false,
        properties: globalSchema.properties,
      },
    },
  };
  const contract = createSafetyEditorSchema({
    type: 'FollowerOverrides',
    schema: overrideSchema,
    referenceSchema: globalSchema,
    currentValue: { EXISTING_EXTENSION: { MAX_VELOCITY: 1 } },
  });

  expect(contract.followers.map((follower) => follower.name)).toEqual([
    'TEST_PROFILE',
    'EXISTING_EXTENSION',
  ]);
  expect(contract.isFollowerDeclared('TEST_PROFILE')).toBe(true);
  expect(contract.isFollowerDeclared('EXISTING_EXTENSION')).toBe(false);
  expect(contract.migrationFollowers.map((follower) => follower.name)).toEqual(['EXISTING_EXTENSION']);
  expect(contract.followers.map((follower) => follower.name)).not.toContain('MC_VELOCITY_CHASE');
  expect(contract.getPropertyByName('MAX_VELOCITY', 'TEST_PROFILE').max).toBe(7.5);
  expect(contract.getPropertyByName('MAX_VELOCITY', 'EXISTING_EXTENSION').editable).toBe(false);
  expect(contract.allowsCustomProperties('TEST_PROFILE')).toBe(false);
});

test('uses a read-only inferred shape when the server object contract is unavailable', () => {
  const unavailable = createSafetyEditorSchema({
    type: 'GlobalLimits',
    schema: null,
    currentValue: { MAX_VELOCITY: 2.5 },
  });
  expect(unavailable.source).toBe('unavailable');
  expect(unavailable.editable).toBe(false);
  expect(unavailable.getPropertyByName('MAX_VELOCITY')).toMatchObject({
    type: 'number',
    editable: false,
  });
  expect(unavailable.getAddableProperties({})).toEqual([]);
  expect(unavailable.allowsCustomProperties()).toBe(false);

  const emptyServerContract = createSafetyEditorSchema({
    type: 'GlobalLimits',
    schema: { type: 'object', properties: {} },
  });
  expect(emptyServerContract.source).toBe('server');
  expect(emptyServerContract.getProperties()).toEqual([]);
});
