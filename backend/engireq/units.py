"""Number and unit recognition shared by the extractor and the validator."""
from __future__ import annotations

import re
from typing import Optional

# canonical unit -> (dimension, surface forms). Matching is case-sensitive on purpose: m != M.
UNIT_TABLE: dict[str, tuple[str, list[str]]] = {
    "degC": ("temperature", ["°C", "° C", "ºC", "℃", "degrees Celsius", "degree Celsius", "degrees C",
                             "deg C", "degC", "degrees centigrade", "Celsius"]),
    "degF": ("temperature", ["°F", "° F", "ºF", "degrees Fahrenheit", "degree Fahrenheit", "deg F", "degF"]),
    "K": ("temperature", ["K", "kelvin", "Kelvin"]),
    "um": ("length", ["µm", "μm", "um", "micrometers", "micrometres", "microns"]),
    "nm": ("length", ["nm", "nanometers", "nanometres"]),
    "mm": ("length", ["mm", "millimeters", "millimetres", "millimeter", "millimetre"]),
    "cm": ("length", ["cm", "centimeters", "centimetres", "centimeter", "centimetre"]),
    "m": ("length", ["m", "meters", "metres", "meter", "metre"]),
    "km": ("length", ["km", "kilometers", "kilometres", "kilometer", "kilometre"]),
    "in": ("length", ["inches", "inch", "in."]),
    "ft": ("length", ["ft", "feet", "foot"]),
    "mg": ("mass", ["mg", "milligrams", "milligram"]),
    "g": ("mass_or_acceleration", ["g", "grams", "gram"]),
    "kg": ("mass", ["kg", "kilograms", "kilogram"]),
    "t": ("mass", ["tonnes", "tonne"]),
    "lb": ("mass", ["lbm", "lb", "lbs", "pounds", "pound"]),
    "ms": ("duration", ["ms", "milliseconds", "millisecond", "msec"]),
    "us": ("duration", ["µs", "μs", "microseconds", "microsecond"]),
    "s": ("duration", ["s", "sec", "secs", "seconds", "second"]),
    "min": ("duration", ["min", "mins", "minutes", "minute"]),
    "h": ("duration", ["h", "hr", "hrs", "hours", "hour"]),
    "day": ("duration", ["days", "day"]),
    "yr": ("duration", ["years", "year"]),
    "N": ("force", ["N", "newtons", "newton", "Newtons", "Newton"]),
    "kN": ("force", ["kN", "kilonewtons", "kilonewton"]),
    "lbf": ("force", ["lbf"]),
    "N.m": ("torque", ["N·m", "N-m", "N.m", "Nm", "newton-meters", "newton meters"]),
    "Pa": ("pressure", ["Pa", "pascals", "pascal"]),
    "kPa": ("pressure", ["kPa", "kilopascals", "kilopascal"]),
    "MPa": ("pressure", ["MPa", "megapascals", "megapascal"]),
    "GPa": ("pressure", ["GPa", "gigapascals", "gigapascal"]),
    "bar": ("pressure", ["bar", "bars"]),
    "mbar": ("pressure", ["mbar", "millibar", "millibars"]),
    "psi": ("pressure", ["psia", "psig", "psi"]),
    "torr": ("pressure", ["torr", "Torr"]),
    "mmHg": ("pressure", ["mmHg", "mm Hg"]),
    "V": ("voltage", ["V", "VDC", "VAC", "Vdc", "Vac", "volts", "volt", "Volts", "Volt"]),
    "mV": ("voltage", ["mV", "millivolts", "millivolt"]),
    "kV": ("voltage", ["kV", "kilovolts", "kilovolt"]),
    "A": ("current", ["A", "amperes", "ampere", "amps", "amp"]),
    "mA": ("current", ["mA", "milliamperes", "milliampere", "milliamps"]),
    "W": ("power", ["W", "watts", "watt", "Watts", "Watt"]),
    "kW": ("power", ["kW", "kilowatts", "kilowatt"]),
    "MW": ("power", ["MW", "megawatts", "megawatt"]),
    "J": ("energy", ["J", "joules", "joule", "Joules"]),
    "kJ": ("energy", ["kJ", "kilojoules", "kilojoule"]),
    "Wh": ("energy", ["Wh", "watt-hours", "watt-hour"]),
    "kWh": ("energy", ["kWh", "kilowatt-hours", "kilowatt-hour"]),
    "Ah": ("charge", ["Ah", "ampere-hours", "ampere-hour", "amp-hours", "amp-hour"]),
    "Hz": ("frequency", ["Hz", "hertz", "Hertz"]),
    "kHz": ("frequency", ["kHz", "kilohertz"]),
    "MHz": ("frequency", ["MHz", "megahertz"]),
    "GHz": ("frequency", ["GHz", "gigahertz"]),
    "ohm": ("resistance", ["Ω", "ohms", "ohm", "Ohms", "Ohm"]),
    "kohm": ("resistance", ["kΩ", "kilohms", "kiloohms"]),
    "Mohm": ("resistance", ["MΩ", "megohms", "megaohms"]),
    "dB": ("sound_or_signal_level", ["dB", "decibels", "decibel"]),
    "dBA": ("sound_level", ["dBA", "dB(A)"]),
    "%": ("ratio", ["%", "percent", "per cent"]),
    "ppm": ("concentration", ["ppm", "parts per million"]),
    "m/s": ("speed", ["m/s", "m/sec", "meters per second", "metres per second"]),
    "km/h": ("speed", ["km/h", "kph"]),
    "m/s2": ("acceleration", ["m/s²", "m/s2", "m/s^2"]),
    "L": ("volume", ["L", "liters", "litres", "liter", "litre"]),
    "mL": ("volume", ["mL", "ml", "milliliters", "millilitres", "milliliter", "millilitre"]),
    "L/min": ("flow_rate", ["L/min", "l/min", "lpm", "liters per minute", "litres per minute"]),
    "W/m2": ("irradiance", ["W/m²", "W/m2", "W/m^2"]),
    "Mbps": ("data_rate", ["Mbps", "Mbit/s"]),
    "kbps": ("data_rate", ["kbps", "kbit/s"]),
    "Gbps": ("data_rate", ["Gbps", "Gbit/s"]),
    "MB": ("data_size", ["MB", "megabytes", "megabyte"]),
    "GB": ("data_size", ["GB", "gigabytes", "gigabyte"]),
    "KB": ("data_size", ["KB", "kilobytes", "kilobyte"]),
    "deg": ("angle", ["°", "degrees", "degree", "deg"]),
}

_SURFACE_TO_CANONICAL = {s: c for c, (_, surfaces) in UNIT_TABLE.items() for s in surfaces}
_ALTERNATION = "|".join(re.escape(s) for s in sorted(_SURFACE_TO_CANONICAL, key=len, reverse=True))
_DENOMINATORS = r"s|sec|min|h|hr|day|m3|m³|m2|m²|m|kg|L|cm2|cm²|K|°C"

# A unit must not run into a following letter or digit, so "5 Apples" has no unit.
UNIT = rf"(?:{_ALTERNATION})(?:/(?:{_DENOMINATORS}))?(?![A-Za-z0-9²³])"
_NUM_CORE = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)"
NUMBER = rf"(?<![\w.,])[-+−–]?{_NUM_CORE}(?![\w]*[.,]\d)"

UNIT_RE = re.compile(UNIT)
NUMBER_RE = re.compile(NUMBER)


def parse_number(surface: str) -> tuple[float, bool]:
    """Return (value, used_decimal_comma). A comma before exactly 3 digits is a thousands separator."""
    cleaned = surface.strip().replace("−", "-").replace("–", "-")
    if re.search(r",\d{3}(?:\D|$)", cleaned):
        return float(cleaned.replace(",", "")), False
    if "," in cleaned:
        return float(cleaned.replace(",", ".")), True
    return float(cleaned), False


def canonical_unit(surface: Optional[str]) -> Optional[str]:
    if not surface:
        return None
    surface = surface.strip()
    if surface in _SURFACE_TO_CANONICAL:
        return _SURFACE_TO_CANONICAL[surface]
    if "/" in surface:
        head, tail = surface.split("/", 1)
        if head in _SURFACE_TO_CANONICAL:
            return f"{_SURFACE_TO_CANONICAL[head]}/{tail.replace('²', '2').replace('³', '3').replace('sec', 's')}"
    return None


def dimension(canonical: Optional[str]) -> Optional[str]:
    if not canonical:
        return None
    if canonical in UNIT_TABLE:
        return UNIT_TABLE[canonical][0]
    return "rate" if "/" in canonical else None


def known_canonical_units() -> list[str]:
    return list(UNIT_TABLE)


def to_absolute_c(value: float, canonical: str) -> Optional[float]:
    """Return a temperature in Celsius for sanity checks, or None when not a temperature."""
    if canonical == "degC":
        return value
    if canonical == "degF":
        return (value - 32) * 5 / 9
    if canonical == "K":
        return value - 273.15
    return None
