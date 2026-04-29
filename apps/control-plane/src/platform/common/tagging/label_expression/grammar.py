from __future__ import annotations

GRAMMAR = """
label_expression ::= or_expr
or_expr          ::= and_expr ("OR" and_expr)*
and_expr         ::= unary_expr ("AND" unary_expr)*
unary_expr       ::= "NOT" unary_expr | primary
primary          ::= comparison | presence | "(" label_expression ")"
comparison       ::= label_key ("=" | "!=") label_value
presence         ::= "HAS" label_key

label_key follows the common tagging LABEL_KEY_PATTERN:
  ^[a-zA-Z][a-zA-Z0-9._-]*$

label_value is an unquoted, non-empty token that cannot contain whitespace,
parentheses, "=", or "!". Values are compared as strings.

Operator precedence:
  NOT > AND > OR

Examples:
  env=production
  env=production AND tier=critical
  HAS owner AND NOT lifecycle=experimental
  (env=production OR env=staging) AND NOT HAS deprecated

Missing-key semantics:
  key=value      -> False when key is missing
  key!=value     -> True when key is missing
  HAS key        -> False when key is missing
  NOT HAS key    -> True when key is missing
"""

