# E.S.T.E.R. architecture

## Name

**E.S.T.E.R. — Everything Seems Totally Easy, Right?**

## Design principle

The user expresses intentions and context. E.S.T.E.R. observes the home, learns from history, selects strategies and explains important decisions.

The LLM is **not** the real-time controller.

## Layers

1. **Home Assistant**
   - Source of entity/device/area state
   - Source of Recorder/history/statistics
   - Actuation layer in future versions

2. **Discovery & classification**
   - Discovers all available HA entities
   - Maps entities to areas/devices
   - Infers broad roles such as climate, energy, hot water, presence, ventilation, irrigation and security
   - User corrections will override inferred classifications

3. **Home model**
   - Rooms/areas
   - Devices and capabilities
   - Environmental state
   - Presence confidence
   - Energy state
   - Learned thermal/usage behavior

4. **Memory**
   - Permanent preferences
   - Temporary context/events
   - Learned behavior
   - Decision history
   - User feedback

5. **Decision engine**
   - Generates candidate strategies
   - Estimates confidence
   - Assigns risk and impact
   - Compares alternatives
   - Requests information when confidence is insufficient for the risk

6. **Shadow executor**
   - v0.1 only
   - Records what E.S.T.E.R. would do
   - Never calls Home Assistant control services

7. **AI layer**
   - Interprets natural language
   - Converts voice/text intentions into structured context/policies
   - Explains decisions
   - Provider-independent interface
   - Gemini is the first planned provider

8. **Future autonomous executor**
   - Disabled in v0.1
   - Will act only inside explicit safety/risk boundaries
   - Low-risk actions may require lower confidence than high-risk actions

## Confidence is not a permission by itself

A decision combines:

- confidence in the interpretation/model
- risk if the decision is wrong
- economic/comfort impact
- reversibility
- safety constraints

Example target thresholds in the current engine:

- low risk: 60%
- medium risk: 80%
- high risk: 93%
- critical: 99%

These are future actuation thresholds. In v0.1 all decisions remain virtual.

## Context examples

Temporary context should be expressible naturally:

- "Ester is home sick today."
- "We are away this weekend."
- "Guests are staying tonight."
- "I will use the gym at 19:00."
- "Do not heat domestic hot water electrically until April."

The AI layer will convert these statements into structured, expiring context or persistent preferences.

## Learning targets

E.S.T.E.R. should eventually learn:

- thermal response per room
- cooling/heating retention
- hot-water demand and recovery
- ventilation effectiveness by season/outdoor conditions
- occupancy/use patterns
- energy cost tradeoffs
- effectiveness of previous decisions

## Safety boundary

Security, alarms, locks, inverter/battery protections and other high-impact controls will retain hard constraints outside the LLM. E.S.T.E.R. may reason about them, but it must never bypass safety constraints.

## v0.1 definition of done

- installs through config flow
- observes all HA entities
- maps areas/devices where available
- classifies broad roles
- persists context and feedback
- produces shadow decisions
- exposes diagnostic sensors
- performs no real device actuation
