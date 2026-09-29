"""Pure economic comparisons for heating choices."""
from __future__ import annotations


def heating_costs(*, electricity_eur_kwh: float | None, gas_eur_m3: float | None,
                  heat_pump_cop: float | None, boiler_efficiency: float | None,
                  gas_kwh_per_m3: float = 10.55) -> dict:
    pdc = gas = None
    if electricity_eur_kwh is not None and heat_pump_cop and heat_pump_cop > 0:
        pdc = electricity_eur_kwh / heat_pump_cop
    if gas_eur_m3 is not None and boiler_efficiency and boiler_efficiency > 0:
        gas = gas_eur_m3 / (gas_kwh_per_m3 * boiler_efficiency)
    preferred = None
    if pdc is not None and gas is not None:
        preferred = "heat_pump" if pdc < gas else "gas"
    return {
        "heat_pump_eur_per_kwh_heat": round(pdc, 4) if pdc is not None else None,
        "gas_eur_per_kwh_heat": round(gas, 4) if gas is not None else None,
        "preferred_source": preferred,
        "difference_eur_per_kwh_heat": round(abs(pdc-gas), 4) if pdc is not None and gas is not None else None,
    }
