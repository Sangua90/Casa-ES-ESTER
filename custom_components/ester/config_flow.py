"""Configuration and opt-in AI options."""
from __future__ import annotations

import re
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN, NAME


class EsterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={"shadow_mode": True})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EsterOptionsFlow()


class EsterOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input["ai_provider"] == "gemini":
                if not user_input.get("api_key", "").strip() or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", user_input.get("model", "")):
                    errors["base"] = "invalid_ai"
            if not errors:
                # Disabling also removes stored credentials from this entry.
                return self.async_create_entry(title="", data=user_input if user_input["ai_provider"] == "gemini" else {"ai_provider": "disabled"})
        schema = vol.Schema({
            vol.Required("ai_provider", default=self.config_entry.options.get("ai_provider", "disabled")): vol.In(["disabled", "gemini"]),
            vol.Optional("api_key"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional("model"): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

