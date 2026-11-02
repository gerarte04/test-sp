"""Детерминированные проверки ответа модели.

Промпт снижает риск выдуманных характеристик, но не исключает его, поэтому каждый ответ
проверяется кодом:

* все числа в сгенерированном тексте должны встречаться во входных данных;
* «рискованные» термины (ГОСТ, IP, поверка, гарантия…) допустимы, только если они есть во входе;
* характеристики, извлечённые из описания, должны подтверждаться дословной цитатой;
* длины SEO-полей и количество поисковых запросов — в рамках требований.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import (
    QUERIES_MAX,
    QUERIES_MIN,
    SEO_DESCRIPTION_MAX,
    SEO_DESCRIPTION_MIN,
    SEO_TITLE_MAX,
    ExtractedSpec,
    LLMCardDraft,
    ProductInput,
)

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Термины, которые модель любит «дорисовывать» в карточки КИП.
# Ключ — регулярное выражение (по нормализованному тексту), значение — как назвать в отчёте.
RISKY_TERMS: dict[str, str] = {
    r"\bгост\b": "ГОСТ",
    r"\bту\s?\d": "ТУ",
    r"\bip\s?\d": "степень защиты IP",
    r"реестр": "реестр СИ",
    r"поверк|поверочн": "поверка",
    r"сертифик": "сертификат",
    r"гаранти": "гарантия",
    r"взрывозащ|\bex\b": "взрывозащита",
    r"\bhart\b": "HART",
    r"modbus": "Modbus",
    r"rs-?485": "RS-485",
    r"нержаве": "нержавеющая сталь",
    r"латун": "латунь",
}


def normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    text = text.replace(" ", " ")
    return " ".join(text.split())


def _canon_number(token: str) -> str:
    token = token.replace(",", ".")
    if "." in token:
        token = token.rstrip("0").rstrip(".") or "0"
    token = token.lstrip("0") or "0"
    if token.startswith("."):
        token = "0" + token
    return token


def numbers_in(text: str) -> set[str]:
    return {_canon_number(m) for m in _NUMBER_RE.findall(text)}


def input_corpus(product: ProductInput) -> str:
    parts = [product.name, product.manufacturer or "", product.description or ""]
    for key, value in product.specs.items():
        parts += [key, value]
    return "\n".join(parts)


def generated_texts(draft: LLMCardDraft) -> dict[str, str]:
    return {
        "SEO-заголовок": draft.seo_title,
        "SEO-описание": draft.seo_description,
        "поисковые запросы": "\n".join(draft.search_queries),
        "блок для менеджера": "\n".join(draft.commercial.audience + draft.commercial.tasks),
    }


@dataclass
class CheckResult:
    problems: list[str] = field(default_factory=list)
    spec_problems: list[str] = field(default_factory=list)
    invalid_specs: list[ExtractedSpec] = field(default_factory=list)

    @property
    def all_problems(self) -> list[str]:
        return self.problems + self.spec_problems

    @property
    def ok(self) -> bool:
        return not self.all_problems


def check_draft(draft: LLMCardDraft, product: ProductInput) -> CheckResult:
    result = CheckResult()
    corpus = input_corpus(product)
    allowed_numbers = numbers_in(corpus)
    corpus_norm = normalize_text(corpus)
    description_norm = normalize_text(product.description or "")

    # Длины и количество
    title_len = len(draft.seo_title.strip())
    if title_len > SEO_TITLE_MAX:
        result.problems.append(
            f"SEO-заголовок длиной {title_len} символов, нужно не более {SEO_TITLE_MAX}."
        )
    if not draft.seo_title.strip():
        result.problems.append("SEO-заголовок пустой.")
    desc_len = len(draft.seo_description.strip())
    if not SEO_DESCRIPTION_MIN <= desc_len <= SEO_DESCRIPTION_MAX:
        result.problems.append(
            f"SEO-описание длиной {desc_len} символов, нужно {SEO_DESCRIPTION_MIN}–{SEO_DESCRIPTION_MAX}."
        )
    n_queries = len([q for q in draft.search_queries if q.strip()])
    if not QUERIES_MIN <= n_queries <= QUERIES_MAX:
        result.problems.append(
            f"Поисковых запросов {n_queries}, нужно {QUERIES_MIN}–{QUERIES_MAX}."
        )

    # Числа и термины, которых нет во входных данных
    for label, text in generated_texts(draft).items():
        unknown = sorted(numbers_in(text) - allowed_numbers, key=lambda x: (len(x), x))
        if unknown:
            result.problems.append(
                f"В поле «{label}» есть числа, которых нет во входных данных: {', '.join(unknown)}."
            )
        text_norm = normalize_text(text)
        risky = sorted(
            {
                name
                for pattern, name in RISKY_TERMS.items()
                if re.search(pattern, text_norm) and not re.search(pattern, corpus_norm)
            }
        )
        if risky:
            result.problems.append(
                f"В поле «{label}» упомянуто то, чего нет во входных данных: {', '.join(risky)}."
            )

    # Характеристики из описания должны подтверждаться цитатой
    for spec in draft.extracted_specs:
        quote_norm = normalize_text(spec.quote)
        value_numbers = numbers_in(spec.value)
        if not quote_norm or quote_norm not in description_norm:
            result.invalid_specs.append(spec)
            result.spec_problems.append(
                f"Характеристика «{spec.name}»: цитата не найдена в описании дословно."
            )
        elif not value_numbers <= numbers_in(spec.quote):
            result.invalid_specs.append(spec)
            result.spec_problems.append(
                f"Характеристика «{spec.name}»: значение «{spec.value}» не совпадает с цитатой."
            )
    return result


def truncate_title(title: str, limit: int = SEO_TITLE_MAX) -> str:
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[: limit + 1]
    cut = cut[: cut.rfind(" ")] if " " in cut else title[:limit]
    return cut.rstrip(" ,;:–—-")
