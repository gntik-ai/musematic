from __future__ import annotations

from platform.common.tagging.label_expression.ast import ASTNode


class LabelExpressionEvaluator:
    async def evaluate(self, ast: ASTNode, target_labels: dict[str, str]) -> bool:
        return ast.evaluate(target_labels)


async def evaluate(ast: ASTNode, target_labels: dict[str, str]) -> bool:
    return await LabelExpressionEvaluator().evaluate(ast, target_labels)
