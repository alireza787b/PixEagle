// dashboard/src/components/config/renderers/TypeRendererRegistry.js
import { PatternType } from '../../../utils/schemaAnalyzer';

/**
 * TypeRendererRegistry - Registry for specialized value renderers
 *
 * Maps pattern types to their corresponding renderer components.
 * Allows for extensibility - new renderers can be registered dynamically.
 */

// Default renderers - will be populated by imports
const defaultRenderers = new Map();

// Custom renderers registered at runtime
const customRenderers = new Map();

/**
 * Register a renderer for a pattern type
 */
export function registerRenderer(patternType, RendererComponent) {
  customRenderers.set(patternType, RendererComponent);
}

/**
 * Get the renderer for a pattern type
 * Returns custom renderer if registered, otherwise default
 */
export function getRenderer(patternType) {
  // Check custom first
  if (customRenderers.has(patternType)) {
    return customRenderers.get(patternType);
  }
  // Then default
  if (defaultRenderers.has(patternType)) {
    return defaultRenderers.get(patternType);
  }
  // Fallback to null - caller should handle
  return null;
}

/**
 * Check if a renderer exists for a pattern
 */
export function hasRenderer(patternType) {
  return customRenderers.has(patternType) || defaultRenderers.has(patternType);
}

/**
 * Check if a pattern can be rendered inline (in table cells)
 */
export function canRenderInline(patternType) {
  return [
    PatternType.PID_TRIPLET,
    PatternType.SCALAR_ARRAY,
    PatternType.STRING_ARRAY,
    PatternType.FLAT_OBJECT
  ].includes(patternType);
}

/**
 * Set default renderers (called during initialization)
 */
export function setDefaultRenderers(renderers) {
  for (const [pattern, Renderer] of Object.entries(renderers)) {
    defaultRenderers.set(pattern, Renderer);
  }
}

/**
 * Clear all custom renderers
 */
export function clearCustomRenderers() {
  customRenderers.clear();
}

/**
 * Get all registered patterns
 */
export function getRegisteredPatterns() {
  const patterns = new Set([
    ...defaultRenderers.keys(),
    ...customRenderers.keys()
  ]);
  return Array.from(patterns);
}

const TypeRendererRegistry = {
  register: registerRenderer,
  get: getRenderer,
  has: hasRenderer,
  canRenderInline,
  setDefaultRenderers,
  clearCustomRenderers,
  getRegisteredPatterns
};

export default TypeRendererRegistry;
