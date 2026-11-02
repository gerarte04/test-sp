from app.guards import check_draft, numbers_in, truncate_title
from app.schemas import LLMCardDraft

from .conftest import good_draft


def test_numbers_normalization():
    assert numbers_in("0–1,6 МПа, G1/2, 100 мм, DM 02") == {"0", "1.6", "1", "2", "100"}
    assert numbers_in("1.60") == {"1.6"}


def test_good_draft_passes(manometer):
    result = check_draft(LLMCardDraft(**good_draft()), manometer)
    assert result.ok, result.all_problems


def test_invented_number_detected(manometer):
    text = good_draft()["seo_description"] + " Рабочая температура до 60 °C."
    result = check_draft(LLMCardDraft(**good_draft(seo_description=text[:1199])), manometer)
    assert any("60" in p for p in result.problems)


def test_invented_terms_detected(manometer):
    draft = good_draft(
        seo_description=good_draft()["seo_description"][:900] + " Соответствует ГОСТ, степень защиты IP 54.",
    )
    problems = " ".join(check_draft(LLMCardDraft(**draft), manometer).problems)
    assert "ГОСТ" in problems and "IP" in problems and "54" in problems


def test_no_false_positive_for_common_words(manometer):
    # «температуру » не должно срабатывать как «ТУ», «тип» — как «IP»
    text = good_draft()["seo_description"][:900] + " Подходит под тип задач, где важно давление и температуру среды не контролируют."
    result = check_draft(LLMCardDraft(**good_draft(seo_description=text)), manometer)
    assert result.ok, result.all_problems


def test_lengths_and_query_count(manometer):
    draft = good_draft(seo_title="М" * 71, seo_description="коротко", search_queries=["a", "b"])
    problems = check_draft(LLMCardDraft(**draft), manometer).problems
    assert len(problems) == 3


def test_extracted_spec_must_be_quoted(manometer):
    draft = good_draft(
        extracted_specs=[
            {"name": "Корпус", "value": "сталь", "quote": "корпус из стали"},
            {"name": "Штуцер", "value": "радиальный, 2 шт", "quote": "Расположение штуцера — радиальное"},
        ]
    )
    result = check_draft(LLMCardDraft(**draft), manometer)
    assert [s.name for s in result.invalid_specs] == ["Корпус", "Штуцер"]


def test_truncate_title():
    title = "Манометр показывающий DM 02 радиальный 0–1,6 МПа G1/2 100 мм класс 1,5 Манотомь"
    short = truncate_title(title)
    assert len(short) <= 70 and title.startswith(short) and not short.endswith(" ")
