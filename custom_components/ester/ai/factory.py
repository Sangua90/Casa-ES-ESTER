"""Single replaceable provider factory; disabled is the default."""
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .gemini import GeminiProvider


def create_provider(hass, options):
    if options.get("ai_provider", "disabled") == "disabled":
        return None
    if options.get("ai_provider") == "gemini":
        return GeminiProvider(session=async_get_clientsession(hass), api_key=options["api_key"], model=options["model"])
    raise ValueError("Unsupported provider")

