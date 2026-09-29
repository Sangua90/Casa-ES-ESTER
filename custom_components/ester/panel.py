"""Native E.S.T.E.R. sidebar panel registration."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig

PANEL_URL = "ester"
STATIC_URL = "/ester_static"
PANEL_ELEMENT = "ester-panel"


async def async_setup_panel_assets(hass) -> None:
    """Register static frontend assets once during integration setup."""
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(frontend_dir), False)]
    )


def async_register_panel(hass) -> None:
    """Register or refresh the E.S.T.E.R. sidebar panel."""
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="E.S.T.E.R.",
        sidebar_icon="mdi:brain",
        frontend_url_path=PANEL_URL,
        config={
            "_panel_custom": {
                "name": PANEL_ELEMENT,
                "embed_iframe": True,
                "trust_external": False,
                "js_url": f"{STATIC_URL}/ester-panel.js",
            }
        },
        require_admin=False,
        update=True,
    )


def async_remove_panel(hass) -> None:
    """Remove only the sidebar panel; static route remains until restart."""
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
