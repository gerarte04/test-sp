import json
from pathlib import Path

import pytest

from app.schemas import ProductInput

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    """LLM-заглушка: отдаёт заранее заготовленные ответы и запоминает промпты."""

    provider = "fake"
    model = "fake-model"

    def __init__(self, *responses: dict):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str, schema: dict) -> dict:
        self.calls.append((system, user))
        return self.responses[min(len(self.calls), len(self.responses)) - 1]


@pytest.fixture
def manometer() -> ProductInput:
    data = json.loads((ROOT / "examples/inputs/products.json").read_text(encoding="utf-8"))[0]
    return ProductInput(**data)


DESCRIPTION_OK = (
    "Манометр показывающий DM 02 производства «Манотомь» предназначен для измерения "
    "избыточного давления неагрессивных, некристаллизующихся жидкостей, газов и паров. "
) * 6  # ~ 1000 символов, без новых чисел


def good_draft(**overrides) -> dict:
    draft = {
        "seo_title": "Манометр показывающий DM 02, 0–1,6 МПа, Манотомь",
        "seo_description": DESCRIPTION_OK.strip(),
        "extracted_specs": [
            {
                "name": "Расположение штуцера",
                "value": "радиальное",
                "quote": "Расположение штуцера — радиальное",
            }
        ],
        "search_queries": ["манометр dm 02", "манометр 0–1,6 мпа g1/2", "купить манометр манотомь dm 02"],
        "commercial": {"audience": ["Службы эксплуатации"], "tasks": ["Контроль давления"]},
        "clarifications": [],
    }
    draft.update(overrides)
    return draft
