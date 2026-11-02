"""Модели данных: вход, ответ LLM и итоговая карточка товара."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NO_DATA = "данных нет"

SEO_TITLE_MAX = 70
SEO_DESCRIPTION_MIN = 800
SEO_DESCRIPTION_MAX = 1200
QUERIES_MIN = 3
QUERIES_MAX = 5


class ProductInput(BaseModel):
    """Нормализованные входные данные о товаре."""

    name: str
    manufacturer: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    description: str | None = None


class InputReport(BaseModel):
    """Что не так с входными данными (генерация при этом возможна)."""

    missing_fields: list[str] = Field(default_factory=list)
    empty_specs: list[str] = Field(default_factory=list)
    missing_typical_specs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def as_clarifications(self) -> list[str]:
        items: list[str] = []
        labels = {"manufacturer": "производитель", "description": "описание", "specs": "характеристики"}
        for field in self.missing_fields:
            items.append(f"Не заполнено поле «{labels.get(field, field)}».")
        for key in self.empty_specs:
            items.append(f"Характеристика «{key}» указана без значения.")
        for key in self.missing_typical_specs:
            items.append(f"Нет данных: {key.lower()}.")
        return items


# --- Ответ LLM (то, что модель возвращает через tool / JSON) ---------------


class ExtractedSpec(BaseModel):
    name: str
    value: str
    quote: str = Field(description="Дословная цитата из описания, подтверждающая значение")


class Commercial(BaseModel):
    audience: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)


class LLMCardDraft(BaseModel):
    seo_title: str
    seo_description: str
    extracted_specs: list[ExtractedSpec] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    commercial: Commercial = Field(default_factory=Commercial)
    clarifications: list[str] = Field(default_factory=list)


# --- Итоговая карточка ------------------------------------------------------


class KeySpec(BaseModel):
    name: str
    value: str
    source: Literal["входные данные", "описание", "нет данных"]


class CardMeta(BaseModel):
    provider: str
    model: str
    attempts: int


class ProductCard(BaseModel):
    product_name: str
    status: Literal["ok", "needs_review"]
    seo_title: str
    seo_title_length: int
    seo_description: str
    seo_description_length: int
    key_specs: list[KeySpec]
    search_queries: list[str]
    commercial: Commercial
    needs_clarification: list[str]
    warnings: list[str]
    meta: CardMeta
