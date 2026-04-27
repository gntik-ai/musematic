# Tool Gateway

The tool gateway controls how agents invoke external capabilities. It evaluates identity, workspace visibility, purpose, policy bundles, budget, and safety checks before executing a tool call.

Tool definitions should include name, purpose, input schema, output schema, side-effect classification, timeout, retry policy, and credential reference. Tool results should include status, structured output, error code, and audit metadata.

Never put provider credentials into tool descriptors or agent packages. Store credentials through the platform secret provider and reference them by logical name.
