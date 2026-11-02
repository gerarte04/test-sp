import pytest

from app.input_validation import InputError, load_json, parse_many, parse_product


def test_invalid_json_reports_position():
    with pytest.raises(InputError) as exc:
        load_json('{"name": "x",}')
    assert exc.value.message == "Некорректный JSON."
    assert "Строка 1" in exc.value.details[0]


def test_empty_input():
    with pytest.raises(InputError):
        load_json("   ")


def test_not_an_object():
    with pytest.raises(InputError):
        parse_product(["a", "b"])


def test_name_required():
    with pytest.raises(InputError) as exc:
        parse_product({"specs": {"класс точности": "1,5"}})
    assert any("name" in d for d in exc.value.details)


def test_needs_specs_or_description():
    with pytest.raises(InputError):
        parse_product({"name": "Манометр", "specs": {}, "description": " "})


def test_wrong_types():
    with pytest.raises(InputError) as exc:
        parse_product({"name": "Манометр", "specs": "0–1,6 МПа", "description": {"a": 1}})
    assert len(exc.value.details) == 2


def test_empty_markers_and_report():
    product, report = parse_product(
        {
            "name": "  Термометр   ТБ-100 ",
            "manufacturer": "",
            "specs": {"диапазон измерений": "0…+120 °C", "класс точности": "-", "питание": None},
            "description": None,
            "price": 100,
        }
    )
    assert product.name == "Термометр ТБ-100"
    assert product.specs == {"диапазон измерений": "0…+120 °C"}
    assert report.missing_fields == ["manufacturer", "description"]
    assert report.empty_specs == ["класс точности", "питание"]
    assert "Диапазон измерений" not in report.missing_typical_specs
    # пустые «класс точности» и «питание» описаны в empty_specs, в типовых не дублируются
    assert "Класс точности / погрешность" not in report.missing_typical_specs
    assert "Питание" not in report.missing_typical_specs
    assert "Интерфейсы / выходной сигнал" in report.missing_typical_specs
    assert report.notes == ["Поле «price» не поддерживается и не использовано."]
    texts = report.as_clarifications()
    assert "Не заполнено поле «производитель»." in texts


def test_numbers_are_accepted_as_values():
    product, _ = parse_product({"name": "X", "specs": {"класс точности": 1.5}})
    assert product.specs["класс точности"] == "1.5"


def test_parse_many():
    assert parse_many({"a": 1}) == [{"a": 1}]
    assert parse_many([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]
    with pytest.raises(InputError):
        parse_many([])
