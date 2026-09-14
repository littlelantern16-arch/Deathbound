"""Deathbound Visual State + Temporal Continuity Engine.

Provider-neutral AI video pipeline built on the existing Deathbound story/shot
architecture. Modules:

- ``paths``            environment-agnostic root + canonical paths
- ``visual_state``     Visual State Manager (per-shot provider-neutral state)
- ``reference_bank``   persistent canon-preserving character reference bank
- ``continuity``       Temporal Continuity Manager (final-frame chaining)
- ``provider_adapter`` provider-neutral generation interface + dry-run provider
- ``manifest``         generation manifest build/validate/persist
- ``qa``               QA validation suite + bounded retry
- ``executor``         episode executor (ordering, chaining, resume, reports)
"""

from .executor import EpisodeExecutor, run_three_shot_vertical_slice
from .visual_state import VisualStateManager
from .reference_bank import CharacterReferenceBank
from .continuity import TemporalContinuityManager
from .manifest import GenerationManifestManager
from .provider_adapter import (
    GenerationRequest,
    GenerationResult,
    VideoProvider,
    get_provider,
    register_provider,
    registered_providers,
)

__all__ = [
    "EpisodeExecutor",
    "run_three_shot_vertical_slice",
    "VisualStateManager",
    "CharacterReferenceBank",
    "TemporalContinuityManager",
    "GenerationManifestManager",
    "GenerationRequest",
    "GenerationResult",
    "VideoProvider",
    "get_provider",
    "register_provider",
    "registered_providers",
]
