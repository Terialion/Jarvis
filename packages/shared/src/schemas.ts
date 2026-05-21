// ============================================================================
// JSON Schema Helpers
// ============================================================================

/** Builder for OpenAI-format tool schemas. */
export interface ToolSchemaDef {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

/**
 * Wrap a tool schema in OpenAI function format.
 * Produces: { type: "function", function: { name, description, parameters } }
 */
export function toOpenAITool(schema: ToolSchemaDef): Record<string, unknown> {
  return {
    type: 'function',
    function: {
      name: schema.name,
      description: schema.description,
      parameters: schema.parameters,
    },
  };
}

/** Deep clone of a plain JSON-compatible value. */
function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/**
 * Sanitize tool schemas for strict backends.
 *
 * Applies the following fixes:
 * - Converts bare string `type` to `{ type: "string" }`
 * - Strips `type: [X, "null"]` arrays (not well supported)
 * - Adds empty `properties: {}` to objects missing it
 * - Removes `required` entries that don't match any property
 */
export function sanitizeToolSchemas(
  tools: Record<string, unknown>[],
): Record<string, unknown>[] {
  return tools.map((tool) => sanitizeToolSchema(tool));
}

function sanitizeToolSchema(
  tool: Record<string, unknown>,
): Record<string, unknown> {
  const cloned = deepClone(tool);

  // Navigate to the parameters schema — may be in OpenAI function format
  let schema: Record<string, unknown> | undefined;

  if (cloned.function && typeof cloned.function === 'object') {
    const fn = cloned.function as Record<string, unknown>;
    if (fn.parameters && typeof fn.parameters === 'object') {
      schema = fn.parameters as Record<string, unknown>;
    }
  } else if (cloned.parameters && typeof cloned.parameters === 'object') {
    schema = cloned.parameters as Record<string, unknown>;
  }

  if (schema) {
    sanitizeSchemaNode(schema);
  }

  return cloned;
}

/**
 * Recursively sanitize a JSON Schema node in place.
 */
function sanitizeSchemaNode(node: Record<string, unknown>): void {
  // Strip union-with-null types: ["string", "null"] → skip (remove type)
  if (Array.isArray(node.type)) {
    delete node.type;
  }

  // Object type must have properties
  if (node.type === 'object' && node.properties === undefined) {
    node.properties = {};
  }

  // Array type must have items
  if (node.type === 'array' && node.items === undefined) {
    node.items = {};
  }

  // Clean required array — remove entries that don't match any property
  if (
    Array.isArray(node.required) &&
    node.properties &&
    typeof node.properties === 'object'
  ) {
    const propKeys = Object.keys(node.properties as Record<string, unknown>);
    node.required = (node.required as string[]).filter((r) =>
      propKeys.includes(r),
    );
    if ((node.required as string[]).length === 0) {
      delete node.required;
    }
  }

  // Recurse into object properties
  if (node.properties && typeof node.properties === 'object') {
    const props = node.properties as Record<string, unknown>;
    for (const key of Object.keys(props)) {
      const value = props[key];
      if (value && typeof value === 'object') {
        sanitizeSchemaNode(value as Record<string, unknown>);
      } else if (typeof value === 'string') {
        // Convert bare string type annotation to { type: string }
        props[key] = { type: value };
      }
    }
  }

  // Recurse into array items
  if (node.items && typeof node.items === 'object') {
    if (Array.isArray(node.items)) {
      for (const item of node.items) {
        if (item && typeof item === 'object') {
          sanitizeSchemaNode(item as Record<string, unknown>);
        }
      }
    } else {
      sanitizeSchemaNode(node.items as Record<string, unknown>);
    }
  }

  // Recurse into anyOf / oneOf / allOf
  for (const key of ['anyOf', 'oneOf', 'allOf']) {
    if (Array.isArray(node[key])) {
      for (const sub of node[key]) {
        if (sub && typeof sub === 'object') {
          sanitizeSchemaNode(sub as Record<string, unknown>);
        }
      }
    }
  }
}

