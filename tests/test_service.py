import pytest

from app.input_validation import parse_product
from app.llm import LLMError, parse_json_object
from app.render import card_to_markdown
from app.schemas import NO_DATA
from app.service import generate_card

from .conftest import FakeClient, good_draft


def test_happy_path(manometer):
    _, report = parse_product(manometer.model_dump())
    client = FakeClient(good_draft())
    card = generate_card(manometer, report, client)

    assert card.status == "ok"
    assert card.meta.attempts == 1
    specs = {s.name: (s.value, s.source) for s in card.key_specs}
    assert specs["Производитель"] == ("Манотомь", "входные данные")
    assert specs["Диапазон измерений"] == ("0–1,6 МПа", "входные данные")
    assert specs["Расположение штуцера"] == ("радиальное", "описание")
    assert specs["Питание"] == (NO_DATA, "нет данных")
    assert specs["Интерфейсы / выходной сигнал"] == (NO_DATA, "нет данных")
    assert "<product_data>" in client.calls[0][1]

    md = card_to_markdown(card)
    assert "## Ключевые характеристики" in md and "| Питание | данных нет | нет данных |" in md


def test_retry_fixes_problems(manometer):
    _, report = parse_product(manometer.model_dump())
    bad = good_draft(seo_title="Манометр DM 02 IP65 0–1,6 МПа")
    client = FakeClient(bad, good_draft())
    card = generate_card(manometer, report, client, max_attempts=2)

    assert card.meta.attempts == 2
    assert card.status == "ok"
    retry_prompt = client.calls[1][1]
    assert "не прошёл проверку" in retry_prompt and "65" in retry_prompt


def test_problems_left_after_retries_become_warnings(manometer):
    _, report = parse_product(manometer.model_dump())
    long_title = "Манометр показывающий DM 02 для воды газов и паров 0–1,6 МПа G1/2 Манотомь"
    bad = good_draft(
        seo_title=long_title,
        extracted_specs=[{"name": "Масса", "value": "0,6 кг", "quote": "масса 0,6 кг"}],
    )
    card = generate_card(manometer, report, FakeClient(bad), max_attempts=2)

    assert card.status == "needs_review"
    assert card.seo_title_length <= 70
    assert all(s.name != "Масса" for s in card.key_specs)
    assert any("сокращён" in w for w in card.warnings)
    assert any("Масса" in w for w in card.warnings)


def test_schema_mismatch_raises(manometer):
    _, report = parse_product(manometer.model_dump())
    with pytest.raises(LLMError):
        generate_card(manometer, report, FakeClient({"foo": "bar"}), max_attempts=2)


def test_incomplete_input_goes_to_clarifications():
    product, report = parse_product(
        {"name": "Термометр ТБ-100", "manufacturer": "", "specs": {"диапазон измерений": "0…+120 °C"}}
    )
    card = generate_card(
        product,
        report,
        FakeClient(
            good_draft(
                seo_title="Термометр ТБ-100, 0…+120 °C",
                seo_description=("Термометр ТБ-100 с диапазоном измерений 0…+120 °C. " * 20)[:1000],
                extracted_specs=[],
                search_queries=["термометр тб-100", "термометр 0 120", "купить термометр тб-100"],
            )
        ),
    )
    assert card.status == "ok"
    assert "Не заполнено поле «производитель»." in card.needs_clarification
    assert ("Производитель", NO_DATA) in [(s.name, s.value) for s in card.key_specs]


def test_parse_json_object():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Вот ответ: {"a": 1} спасибо') == {"a": 1}
    with pytest.raises(LLMError):
        parse_json_object("[1, 2]")
    with pytest.raises(LLMError):
        parse_json_object("")
