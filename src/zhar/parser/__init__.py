"""zhar parser — %%ZHAR.*%% template language public API."""

from zhar.parser.cond import CondError, eval_condition_groups, eval_expr
from zhar.parser.render import ParseContext, ParseError, render, render_template

# Legacy aliases so existing code importing TemplateContext / TemplateError still works
TemplateContext = ParseContext
TemplateError = ParseError

__all__ = [
    "ParseContext",
    "ParseError",
    "render",
    "TemplateContext",
    "TemplateError",
    "render_template",
    "CondError",
    "eval_expr",
    "eval_condition_groups",
]
