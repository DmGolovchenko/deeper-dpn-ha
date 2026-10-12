"""Labels for dynamic route options; entity names use native HA translations."""
TEXT = {
    "en": {
        "direct": "Direct connection", "general": "General routing", "unavailable": "unavailable",
        "disabled": "Direct", "smart": "Smart", "full": "Full", "mixed": "Different routes",
        "SE": "Sweden", "DE": "Germany", "TR": "Turkey", "FR": "France",
        "US": "USA", "CA": "Canada", "CH": "Switzerland", "IT": "Italy",
        "SG": "Singapore", "CN": "China", "AE": "UAE",
    },
    "ru": {
        "direct": "Прямое подключение", "general": "Общая маршрутизация", "unavailable": "недоступен",
        "disabled": "Прямая", "smart": "Умная", "full": "Полная", "mixed": "Разные маршруты",
        "SE": "Швеция", "DE": "Германия", "TR": "Турция", "FR": "Франция",
        "US": "США", "CA": "Канада", "CH": "Швейцария", "IT": "Италия",
        "SG": "Сингапур", "CN": "Китай", "AE": "ОАЭ",
    },
}


def text(key, language="en", default=None):
    language = language.replace("_", "-").split("-")[0].lower()
    return TEXT.get(language, TEXT["en"]).get(key, default if default is not None else key)


def mode_options(language="en"):
    return {mode: text(mode, language) for mode in ("disabled", "smart", "full")}


def ha_language(hass):
    return getattr(getattr(hass, "config", None), "language", "en") or "en"
