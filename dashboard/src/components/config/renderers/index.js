// dashboard/src/components/config/renderers/index.js
/**
 * Renderers Index - Export all specialized renderers and set up registry
 */

import { PatternType } from '../../../utils/schemaAnalyzer';
import TypeRendererRegistry, { setDefaultRenderers } from './TypeRendererRegistry';

// Import all renderers
import PIDRenderer from './PIDRenderer';
import AxisPIDRenderer from './AxisPIDRenderer';
import ScalarArrayRenderer from './ScalarArrayRenderer';
import GenericObjectRenderer from './GenericObjectRenderer';

// Register default renderers
console.log('Registering renderers with PatternType:', PatternType);
setDefaultRenderers({
  [PatternType.PID_TRIPLET]: PIDRenderer,
  [PatternType.AXIS_PID_GROUP]: AxisPIDRenderer,
  [PatternType.SCALAR_ARRAY]: ScalarArrayRenderer,
  [PatternType.STRING_ARRAY]: ScalarArrayRenderer,
  [PatternType.FLAT_OBJECT]: GenericObjectRenderer,
  [PatternType.NESTED_OBJECT]: GenericObjectRenderer,
  [PatternType.GAIN_SCHEDULE]: GenericObjectRenderer,
});
console.log('TypeRendererRegistry initialized. Registered patterns:', TypeRendererRegistry.getRegisteredPatterns());

// Re-export all renderers
export {
  PIDRenderer,
  AxisPIDRenderer,
  ScalarArrayRenderer,
  GenericObjectRenderer,
  TypeRendererRegistry
};

// Export pattern types for convenience
export { PatternType } from '../../../utils/schemaAnalyzer';

// Default export is the registry
export default TypeRendererRegistry;
