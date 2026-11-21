import yaml from 'js-yaml';
import { isPlainObject } from './configEditorSchemaUtils';

const MAX_FILE_SIZE = 1024 * 1024;
const MAX_NODES = 20000;

export async function readConfigYaml(file) {
  if (!/\.ya?ml$/i.test(file.name)) throw new Error('Choose a .yaml or .yml configuration file.');
  if (file.size > MAX_FILE_SIZE) throw new Error('Choose a configuration file smaller than 1 MB.');
  const text = typeof file.text === 'function' ? await file.text() : await new Response(file).text();
  let mapping;
  try {
    mapping = yaml.load(text, { schema: yaml.JSON_SCHEMA });
  } catch (error) {
    const line = error.mark?.line;
    throw new Error(line == null ? 'The file contains invalid YAML.' : `Invalid YAML on line ${line + 1}.`);
  }
  if (!isPlainObject(mapping)) throw new Error('The YAML file must contain a settings mapping.');
  let count = 0;
  const validate = (value, depth) => {
    if (++count > MAX_NODES || depth > 16) throw new Error('This configuration is too large to review.');
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('All configuration numbers must be finite.');
    if (value && typeof value === 'object') {
      for (const item of Object.values(value)) validate(item, depth + 1);
    }
  };
  validate(mapping, 0);
  return mapping;
}
