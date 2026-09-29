"""Native Home Assistant conversation agent for teaching E.S.T.E.R. in Shadow Mode."""
from __future__ import annotations

from typing import Literal

from homeassistant.components import conversation
from homeassistant.const import MATCH_ALL
from homeassistant.helpers import intent

from .const import DOMAIN
from .language_pipeline import interpret_and_store
from .questions import apply_answer
from .snapshots import create_snapshot
from homeassistant.util import dt as dt_util

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([EsterConversationEntity(entry.runtime_data, entry)])


class EsterConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
):
    """Voice/text agent that learns context but never controls Home Assistant."""

    _attr_name = "E.S.T.E.R."
    _attr_supported_features = conversation.ConversationEntityFeature(0)
    _attr_supports_streaming = False

    def __init__(self, coordinator, entry):
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_conversation"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "E.S.T.E.R.",
            "manufacturer": "Casa ES",
            "model": "Intelligent Home Manager",
            "sw_version": "1.4.0",
        }

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(self, user_input, chat_log):
        try:
            voice_question_id = self.coordinator.storage.data.get("voice_question_id")
            if voice_question_id:
                async with self.coordinator.storage.lock:
                    create_snapshot(
                        self.coordinator.storage.data,
                        dt_util.utcnow(),
                        "Prima di risposta vocale",
                        voice_question_id,
                    )
                    interpretation = apply_answer(
                        self.coordinator.storage.data,
                        voice_question_id,
                        user_input.text,
                        dt_util.utcnow(),
                    )
                    self.coordinator.storage.data["voice_question_id"] = None
                    await self.coordinator.storage.async_save()
                await self.coordinator.async_request_refresh()
                speech = "Ho registrato la risposta alla domanda aperta. " + interpretation.get("summary", "")
                response = intent.IntentResponse(language=user_input.language)
                response.async_set_speech(speech)
                return conversation.ConversationResult(
                    response=response,
                    conversation_id=user_input.conversation_id,
                    continue_conversation=False,
                )

            result = await interpret_and_store(
                self.hass,
                self.coordinator,
                user_input.text,
            )
            memory = result.get("memory_result", {})
            applied = memory.get("applied", "knowledge_note")
            provider = result.get("provider", "local")
            speech = {
                "preference": "Ho memorizzato la preferenza.",
                "context": "Ho aggiornato il contesto della casa.",
                "usage_profile": "Ho memorizzato la routine di utilizzo.",
                "knowledge_note": "Ho conservato l'informazione. Se servirà, ti farò una domanda per chiarirla.",
            }.get(applied, "Ho registrato l'informazione.")
            if provider == "gemini":
                speech += " Ho usato Gemini solo per interpretare il linguaggio."
        except Exception:
            speech = "Non sono riuscita a interpretare con sufficiente sicurezza. Non ho modificato la memoria."

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(speech)
        return conversation.ConversationResult(
            response=response,
            conversation_id=user_input.conversation_id,
            continue_conversation=False,
        )
