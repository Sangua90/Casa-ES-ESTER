# E.S.T.E.R.

**Everything Seems Totally Easy, Right?**

E.S.T.E.R. is an intelligent home-management layer for Home Assistant.

## Current status

**v0.1.0 — Shadow Mode only**

E.S.T.E.R. observes Home Assistant, builds a model of the home and produces virtual decisions with confidence, risk and reasoning. It does **not** call device services or change real device states.

## v0.1 goals

- Automatic discovery of Home Assistant entities, devices and areas
- Entity classification by domain and inferred role
- Shadow decision engine
- Confidence / risk / impact model
- Persistent decision log
- User feedback-ready data model
- Provider-independent AI interface, with Gemini planned as the first provider
- Safe foundation for future modules: energy, climate, hot water, ventilation, irrigation, lighting, presence and security

## Installation

Copy `custom_components/ester` into Home Assistant's `custom_components` directory and restart Home Assistant.

Then add **E.S.T.E.R.** from **Settings → Devices & services → Add integration**.

No real device control is enabled in this version.
