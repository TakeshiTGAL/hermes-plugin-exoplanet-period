"""Confirmed exoplanet period, discovery year, and discovery facility."""
from pathlib import Path


def make_handler(name):
    """Hermes accepts a string tool result."""

    def _run(args, **_kwargs):
        if __package__:
            from .service import dump, invoke
        else:
            from service import dump, invoke
        return dump(invoke(name, args or {}))

    return _run


_SKILL_DESCRIPTION = (
    "Confirmed exoplanet orbital period by name. Before web_search, use tool_search "
    "and tool_call exoplanet_lookup. A non-exact name stays a candidate."
)


def register(ctx) -> None:
    if __package__:
        from .cli import handle, setup_parser
        from .prefix import remember_profile_name
        from .schemas import ALL, TOOLSET
        from .service import TOOLS
    else:
        from cli import handle, setup_parser
        from prefix import remember_profile_name
        from schemas import ALL, TOOLSET
        from service import TOOLS

    try:
        reported = ctx.profile_name
    except Exception:
        reported = None
    remember_profile_name(reported)

    for schema in ALL:
        if schema["name"] not in TOOLS:
            continue
        ctx.register_tool(
            name=schema["name"],
            toolset=TOOLSET,
            schema=schema,
            handler=make_handler(schema["name"]),
        )
    ctx.register_cli_command(
        name="exoplanet-period",
        help="Look up one confirmed exoplanet period and watch one morning date",
        setup_fn=setup_parser,
        handler_fn=handle,
        description="Local commands for one exoplanet period and the morning watch.",
    )
    try:
        ctx.register_skill(
            "exoplanet-period",
            Path(__file__).resolve().parent / "skills" / "exoplanet-period" / "SKILL.md",
            description=_SKILL_DESCRIPTION,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("exoplanet-period skill was not registered", exc_info=True)
