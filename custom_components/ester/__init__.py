"""E.S.T.E.R. permanent Shadow Mode integration."""
from __future__ import annotations

from homeassistant.const import Platform

from .coordinator import EsterCoordinator
from .services import register_services
from .panel import async_setup_panel_assets, async_register_panel, async_remove_panel
from .storage import EsterStorage


async def async_setup(hass, config):
    register_services(hass)
    await async_setup_panel_assets(hass)
    return True


async def async_setup_entry(hass, entry):
    storage = EsterStorage(hass)
    await storage.async_load()
    coordinator = EsterCoordinator(hass, entry, storage)
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()
    async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.TEXT, Platform.CONVERSATION])
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR, Platform.TEXT, Platform.CONVERSATION]):
        async with entry.runtime_data.storage.lock:
            await entry.runtime_data.storage.async_save()
        async_remove_panel(hass)
        return True
    return False
