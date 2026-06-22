from futures_mvp.modules.paper_trading.research_mvp import (
    MOCK_ONLY_TARGET,
    PaperAllocation,
    PaperConsistencyReport,
    PaperFill,
    PaperOrder,
    PaperPnL,
    PaperPortfolio,
    PaperPosition,
    PaperReport,
    PaperResearchRuntime,
    PaperResearchSession,
    PaperRuntimeResult,
    PaperRuntimeStatus,
    PaperSessionLifecycle,
    PaperSessionResult,
)

_LEGACY_INTERNAL_NAMES = {
    "PaperJobConfig": ("futures_mvp.modules.paper_trading.job", "PaperJobConfig"),
}

__all__ = [
    "MOCK_ONLY_TARGET",
    "PaperAllocation",
    "PaperConsistencyReport",
    "PaperFill",
    "PaperOrder",
    "PaperPnL",
    "PaperPortfolio",
    "PaperPosition",
    "PaperReport",
    "PaperResearchRuntime",
    "PaperResearchSession",
    "PaperRuntimeResult",
    "PaperRuntimeStatus",
    "PaperSessionLifecycle",
    "PaperSessionResult",
]


def __getattr__(name: str) -> object:
    legacy = _LEGACY_INTERNAL_NAMES.get(name)
    if legacy is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = legacy
    from importlib import import_module

    return getattr(import_module(module_name), attribute)
