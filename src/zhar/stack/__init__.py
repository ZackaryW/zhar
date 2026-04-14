"""Stack support for bucket-backed agent, instruction, skill, and hook sync."""
# %ZHAR:4aa6%

from zhar.stack.bucket import BucketManager
from zhar.stack.registry import StackRegistry
from zhar.stack.sync import SyncResult, sync_stack
from zhar.parser import TemplateContext, TemplateError, render_template

__all__ = [
    "BucketManager",
    "StackRegistry",
    "SyncResult",
    "TemplateContext",
    "TemplateError",
    "render_template",
    "sync_stack",
]