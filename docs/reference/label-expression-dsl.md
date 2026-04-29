# Label Expression DSL

Label expressions are policy match conditions evaluated against a target entity's labels. They are parsed at policy save time and compiled into a cached AST for gateway evaluation.

## Grammar

```bnf
label_expression ::= or_expr
or_expr          ::= and_expr ("OR" and_expr)*
and_expr         ::= not_expr ("AND" not_expr)*
not_expr         ::= "NOT" not_expr | primary
primary          ::= comparison | presence | "(" label_expression ")"
comparison       ::= IDENT ("=" | "!=") IDENT
presence         ::= "HAS" IDENT
IDENT            ::= [a-zA-Z][a-zA-Z0-9._-]*
```

Operator precedence is `NOT`, then `AND`, then `OR`. Parentheses override precedence.

## Missing Keys

| Expression | Missing key result |
| --- | --- |
| `key=value` | `false` |
| `key!=value` | `true` |
| `HAS key` | `false` |
| `NOT HAS key` | `true` |

## Examples

```text
env=production
env=production AND tier=critical
(env=production OR env=staging) AND NOT lifecycle=experimental
HAS owner AND owner!=unknown
```

Malformed expressions are rejected before the policy version is saved. Error responses include `line`, `col`, `token`, and `message` so authoring surfaces can point at the failing token.
