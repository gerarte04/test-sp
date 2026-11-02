"""Разбор и проверка входного JSON о товаре.

Две категории проблем:
* ``InputError`` — генерировать карточку нельзя (битый JSON, нет названия,
  нет ни характеристик, ни описания, неверные типы);
* ``InputReport`` — генерировать можно, но часть данных отсутствует
  и должна попасть в блок «Требует уточнения».
"""

from __future__ import annotations

import json
from typing import Any

from .schemas import InputReport, ProductInput

# Значения, которые контент-менеджеры часто ставят вместо пустоты.
_EMPTY_MARKERS = {"", "-", "—", "–", "н/д", "нет данных", "данных нет", "n/a", "na", "null", "none", "?"}

# Типовые характеристики КИП, наличие которых проверяем по ключам specs.
# Ключ — подпись для отчёта, значение — подстроки, по которым узнаём характеристику.
TYPICAL_SPECS: dict[str, tuple[str, ...]] = {
    "Диапазон измерений": ("диапазон", "предел", "range"),
    "Класс точности / погрешность": ("точност", "погрешн", "accuracy"),
    "Питание": ("питани", "напряжени", "power", "supply"),
    "Корпус / исполнение": ("корпус", "исполнени", "ip", "защит", "housing"),
    "Интерфейсы / выходной сигнал": ("интерфейс", "выход", "сигнал", "протокол", "output", "interface"),
}


class InputError(ValueError):
    """Входные данные нельзя обработать."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.message, "details": self.details}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _EMPTY_MARKERS
    return False


def _clean_str(value: Any, field: str, errors: list[str]) -> str | None:
    if _is_empty(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        errors.append(f"Поле «{field}» должно быть строкой, получено: {type(value).__name__}.")
        return None
    return " ".join(str(value).split())


def load_json(raw: str | bytes) -> Any:
    """Читает JSON-текст и возвращает объект; при ошибке — понятное InputError."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError("Входные данные не в кодировке UTF-8.") from exc
    if not raw or not raw.strip():
        raise InputError("Пустой ввод: ожидается JSON с данными о товаре.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(
            "Некорректный JSON.",
            [f"Строка {exc.lineno}, столбец {exc.colno}: {exc.msg}."],
        ) from exc


def parse_product(data: Any) -> tuple[ProductInput, InputReport]:
    """Проверяет один товар (dict) и возвращает нормализованные данные и отчёт."""
    if not isinstance(data, dict):
        raise InputError(
            "Ожидается JSON-объект товара.",
            [f"Получено значение типа {type(data).__name__}."],
        )

    errors: list[str] = []
    report = InputReport()

    known = {"name", "manufacturer", "specs", "description"}
    unknown = sorted(set(data) - known)

    name = _clean_str(data.get("name"), "name", errors)
    if name is None and not any("name" in e for e in errors):
        errors.append("Не указано название товара (поле «name») — без него карточку не собрать.")

    manufacturer = _clean_str(data.get("manufacturer"), "manufacturer", errors)
    if manufacturer is None:
        report.missing_fields.append("manufacturer")

    description = _clean_str(data.get("description"), "description", errors)
    if description is None:
        report.missing_fields.append("description")

    specs: dict[str, str] = {}
    raw_specs = data.get("specs")
    if raw_specs is None:
        report.missing_fields.append("specs")
    elif not isinstance(raw_specs, dict):
        errors.append(
            "Поле «specs» должно быть объектом вида {\"характеристика\": \"значение\"}, "
            f"получено: {type(raw_specs).__name__}."
        )
    else:
        for raw_key, raw_value in raw_specs.items():
            key = " ".join(str(raw_key).split())
            if not key:
                continue
            value = _clean_str(raw_value, f"specs.{key}", errors)
            if value is None:
                report.empty_specs.append(key)
            else:
                specs[key] = value
        if not raw_specs:
            report.missing_fields.append("specs")

    if errors:
        raise InputError("Входные данные содержат ошибки.", errors)

    if not specs and description is None:
        raise InputError(
            "Недостаточно данных для карточки.",
            ["Нужны хотя бы характеристики (specs) или описание (description)."],
        )

    # Пустые характеристики уже попадут в отчёт отдельной строкой — не дублируем их.
    lowered_keys = [k.lower() for k in [*specs, *report.empty_specs]]
    for label, needles in TYPICAL_SPECS.items():
        if not any(n in key for key in lowered_keys for n in needles):
            report.missing_typical_specs.append(label)

    for key in unknown:
        report.notes.append(f"Поле «{key}» не поддерживается и не использовано.")

    product = ProductInput(name=name or "", manufacturer=manufacturer, specs=specs, description=description)
    return product, report


def parse_many(data: Any) -> list[Any]:
    """Файл может содержать один товар (объект) или список товаров."""
    if isinstance(data, list):
        if not data:
            raise InputError("Пустой список товаров.")
        return data
    return [data]
