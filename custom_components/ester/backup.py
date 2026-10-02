"""Flush complete memory and a recovery generation before native HA backups."""
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_pre_backup(hass: HomeAssistant) -> None:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is None:
            continue
        async with coordinator.storage.lock:
            await coordinator.storage.async_save()
            await coordinator.storage.async_create_backup()


async def async_post_backup(hass: HomeAssistant) -> None:
    """No paused operations to resume: persistence uses atomic HA stores."""
