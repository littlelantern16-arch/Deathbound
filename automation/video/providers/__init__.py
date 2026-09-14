"""Deathbound local provider adapters.

Importing this package registers all bundled local providers via
``@register_provider``. Adding a real backend later = one new adapter file
plus one import line here — no engine changes.

Note: adapter modules live at ``automation/video/<name>_provider.py`` (the
task-mandated location), so they are imported by absolute path.
"""

from automation.video import ltx_provider  # noqa: F401  (registers "ltx-local")

__all__ = ["ltx_provider"]
