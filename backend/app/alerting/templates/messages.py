"""Action-code -> {en, sw} message templates + a ``render`` helper.

Every template is short, plain-language, and ALWAYS states the action the farmer
should take (so an SMS/USSD reader knows what to do without opening an app). Templates
are ``str.format``-style and tolerate missing context keys via a defaulting dict, so a
template can reference ``{greenhouse}`` / ``{value}`` etc. without exploding when the
dispatcher passes a sparse context.

Action codes map 1:1 to the risk engine's ``RiskResult.action_code`` values for late
blight, Tuta absoluta, microclimate (vent / fungal / irrigate), nutrient and water/leak.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.db.models.common import Language

log = get_logger("alerting.templates")

# action_code -> {"en": ..., "sw": ...}. Keep both languages action-first.
MESSAGE_TEMPLATES: dict[str, dict[str, str]] = {
    # ---- Late blight ----
    "blight_high": {
        "en": (
            "BLIGHT RISK (HIGH) at {greenhouse}: {wet_hours}h of leaf-wetness. "
            "Ventilate the greenhouse now and apply a preventive fungicide tonight."
        ),
        "sw": (
            "HATARI YA BAKTERIA/KUVU (KUBWA) {greenhouse}: saa {wet_hours} za unyevu "
            "kwenye majani. Pitisha hewa ndani sasa na nyunyizia dawa ya kuzuia kuvu usiku huu."
        ),
    },
    "blight_medium": {
        "en": (
            "Blight risk building at {greenhouse} ({wet_hours}h wet). Open vents to dry "
            "the canopy and prepare to spray a preventive fungicide."
        ),
        "sw": (
            "Hatari ya kuvu inaongezeka {greenhouse} (saa {wet_hours} za unyevu). Fungua "
            "matundu ya hewa ili kukausha majani na jiandae kunyunyizia dawa ya kuzuia."
        ),
    },
    "blight_forecast": {
        "en": (
            "Overnight blight window forming at {greenhouse}. Ventilate early this "
            "evening and have preventive fungicide ready before the leaves stay wet."
        ),
        "sw": (
            "Mazingira ya kuvu yanaweza kutokea usiku {greenhouse}. Pitisha hewa mapema "
            "jioni na uwe na dawa ya kuzuia kuvu kabla majani hayajakaa na unyevu."
        ),
    },
    # ---- Tuta absoluta ----
    "tuta_generation": {
        "en": (
            "TUTA ABSOLUTA: a new generation is emerging at {greenhouse}. The spray "
            "window is open now - scout the leaves, check pheromone traps and treat."
        ),
        "sw": (
            "TUTA ABSOLUTA: kizazi kipya kinaibuka {greenhouse}. Wakati wa kunyunyizia "
            "dawa umefika sasa - kagua majani, angalia mitego ya pheromone na utibu."
        ),
    },
    "tuta_trap": {
        "en": (
            "High Tuta trap catch at {greenhouse} ({trap_count} moths). Pest pressure is "
            "rising - scout for leaf mines and spray the recommended treatment."
        ),
        "sw": (
            "Mitego ya Tuta imeshika wadudu wengi {greenhouse} (nondo {trap_count}). "
            "Shinikizo la wadudu linaongezeka - kagua majani na unyunyizie dawa inayofaa."
        ),
    },
    # ---- Microclimate ----
    "vent_now": {
        "en": (
            "TOO HOT at {greenhouse}: {value}C. Open the vents and switch on fans now to "
            "cool the crop and prevent heat stress."
        ),
        "sw": (
            "JOTO KALI {greenhouse}: {value}C. Fungua matundu ya hewa na washa feni sasa "
            "ili kupoza mazao na kuzuia mkazo wa joto."
        ),
    },
    "fungal_warning": {
        "en": (
            "Humidity high at {greenhouse} ({value}%). Ventilate to lower humidity - "
            "damp air encourages fungal disease on the leaves."
        ),
        "sw": (
            "Unyevu wa hewa uko juu {greenhouse} (%{value}). Pitisha hewa kupunguza unyevu "
            "- hewa yenye unyevu huchochea magonjwa ya kuvu kwenye majani."
        ),
    },
    "irrigate_now": {
        "en": (
            "Soil is dry at {greenhouse} ({value}% moisture). Irrigate now so the crop "
            "does not wilt and lose yield."
        ),
        "sw": (
            "Udongo umekauka {greenhouse} (unyevu %{value}). Mwagilia maji sasa ili mazao "
            "yasinyauke na kupoteza mavuno."
        ),
    },
    # ---- Nutrient ----
    "fertigate": {
        "en": (
            "Nutrient deficit at {greenhouse} ({nutrient} low). Adjust the fertigation "
            "mix toward the {stage} stage target to keep the crop feeding."
        ),
        "sw": (
            "Upungufu wa virutubisho {greenhouse} ({nutrient} chini). Rekebisha mchanganyiko "
            "wa mbolea ya maji kufikia lengo la hatua ya {stage} ili mazao yaendelee kula."
        ),
    },
    # ---- Water ----
    "water_leak": {
        "en": (
            "POSSIBLE LEAK at {greenhouse}: water is flowing ({flow} L/min) with no "
            "scheduled irrigation. Check the lines and shut the valve to stop the loss."
        ),
        "sw": (
            "HUENDA KUNA UVUJAJI {greenhouse}: maji yanapita ({flow} L/dakika) bila "
            "ratiba ya umwagiliaji. Kagua mabomba na funga valvu kusimamisha upotevu."
        ),
    },
    "water_irrigate": {
        "en": (
            "Crop needs water at {greenhouse}: soil low and no flow detected. Start "
            "irrigation now to avoid water stress."
        ),
        "sw": (
            "Mazao yanahitaji maji {greenhouse}: udongo umekauka na hakuna mtiririko. "
            "Anza umwagiliaji sasa ili kuepuka mkazo wa maji."
        ),
    },
    # ---- Generic fallback ----
    "generic": {
        "en": "Alert at {greenhouse}: {title}. Please check the greenhouse and act.",
        "sw": "Tahadhari {greenhouse}: {title}. Tafadhali kagua kijani na uchukue hatua.",
    },
}


class _DefaultingDict(dict):
    """``str.format_map`` helper: missing keys render as their own name placeholder."""

    def __missing__(self, key: str) -> str:  # noqa: D105
        return "-"


def render(action_code: str, language: Language | str, context: dict | None = None) -> str:
    """Render the template for ``action_code`` in ``language`` filled with ``context``.

    Falls back to the ``generic`` template for unknown action codes, and to English
    when an unknown language is supplied. Missing context keys render as ``-`` rather
    than raising, so the caller never has to provide a complete context.
    """
    lang = language.value if isinstance(language, Language) else str(language)
    lang = lang if lang in {"en", "sw"} else "en"

    template_set = MESSAGE_TEMPLATES.get(action_code)
    if template_set is None:
        log.debug("alerting.template.unknown_action", action_code=action_code)
        template_set = MESSAGE_TEMPLATES["generic"]

    template = template_set.get(lang) or template_set["en"]
    safe_ctx = _DefaultingDict(context or {})
    try:
        return template.format_map(safe_ctx)
    except (KeyError, IndexError, ValueError):  # pragma: no cover - defensive
        return template
