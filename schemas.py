"""Tool schema. The description is one string so the first sentence stays intact."""

TOOLSET = "exoplanet-period"

EXOPLANET_LOOKUP = {
    "name": "exoplanet_lookup",
    "description": (
        "Look up one confirmed exoplanet orbital period by name. "
        "The result gives the official name, the disposition, the period in days, "
        "the discovery year, and the discovery facility. "
        "A name that is not exact stays a candidate and has no period."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Planet name, such as WASP-12 b.",
            },
        },
    },
}

ALL = [EXOPLANET_LOOKUP]
