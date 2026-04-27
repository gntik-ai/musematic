# Visibility and Tools

Visibility controls who can discover and invoke an agent. Tools control what the agent can call during execution. Configure both before publishing.

Start with private workspace visibility, then widen access after certification. For tools, grant only the capabilities required by the purpose statement. Secrets should resolve through the platform secret provider; never embed credentials in prompts, packages, or metadata.

If an invocation fails because a tool is blocked, inspect the policy bundle before changing agent code.
