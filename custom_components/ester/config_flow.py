"""Config flow for E.S.T.E.R."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, NAME


class EsterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure E.S.T.E.R."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Create the single E.S.T.E.R. instance."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=NAME,
                data={
                    "shadow_mode": True,
                    "ai_provider": "gemini",
                },
            )

        schema = vol.Schema({})
        return self.async_show_form(step_id="user", data_schema=schema)
