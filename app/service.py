"""Оркестрация: проверка входа → промпт → LLM → проверки → (повтор) → карточка."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from .guards import check_draft, normalize_text, truncate_title
from .input_validation import TYPICAL_SPECS
from .llm import LLMClient, LLMError
from .prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt, output_schema
from .schemas import (
    NO_DATA,
    QUERIES_MAX,
    CardMeta,
    ExtractedSpec,
    InputReport,
    KeySpec,
    LLMCardDraft,
    ProductCard,
    ProductInput,
)

log = logging.getLogger(__name__)


def generate_card(
    product: ProductInput,
    report: InputReport,
    client: LLMClient,
    max_attempts: int = 2,
) -> ProductCard:
    user_prompt = build_user_prompt(product, report)
    schema = output_schema()

    prompt = user_prompt
    draft: LLMCardDraft | None = None
    raw: dict = {}
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        raw = client.generate(SYSTEM_PROMPT, prompt, schema)
        try:
            draft = LLMCardDraft.model_validate(raw)
        except ValidationError as exc:
            problems = [f"Ответ не соответствует схеме: {e['loc']}: {e['msg']}" for e in exc.errors()]
            log.warning("attempt %s: invalid schema: %s", attempts, problems)
            draft = None
        else:
            check = check_draft(draft, product)
            if check.ok:
                break
            problems = check.all_problems
            log.info("attempt %s: %d problems: %s", attempts, len(problems), problems)
        if attempts < max_attempts:
            prompt = build_retry_prompt(user_prompt, raw, problems)

    if draft is None:
        raise LLMError("Модель вернула ответ, не соответствующий ожидаемой структуре.")

    return _assemble(product, report, draft, client, attempts)


def _assemble(
    product: ProductInput,
    report: InputReport,
    draft: LLMCardDraft,
    client: LLMClient,
    attempts: int,
) -> ProductCard:
    check = check_draft(draft, product)
    warnings = list(check.problems)
    for spec in check.invalid_specs:
        warnings.append(
            f"Характеристика «{spec.name}: {spec.value}» не подтверждена описанием и не включена в карточку."
        )

    title = truncate_title(draft.seo_title)
    if title != " ".join(draft.seo_title.split()):
        warnings.append("SEO-заголовок автоматически сокращён до 70 символов — проверьте формулировку.")

    queries = _dedupe([q.strip() for q in draft.search_queries if q.strip()])[:QUERIES_MAX]

    key_specs = _build_key_specs(product, report, draft, check.invalid_specs)

    clarifications = _dedupe(report.as_clarifications() + report.notes + draft.clarifications)

    return ProductCard(
        product_name=product.name,
        status="needs_review" if warnings else "ok",
        seo_title=title,
        seo_title_length=len(title),
        seo_description=draft.seo_description.strip(),
        seo_description_length=len(draft.seo_description.strip()),
        key_specs=key_specs,
        search_queries=queries,
        commercial=draft.commercial,
        needs_clarification=clarifications,
        warnings=warnings,
        meta=CardMeta(provider=client.provider, model=client.model, attempts=attempts),
    )


def _build_key_specs(
    product: ProductInput,
    report: InputReport,
    draft: LLMCardDraft,
    invalid: list[ExtractedSpec],
) -> list[KeySpec]:
    """Список характеристик собирается кодом, а не моделью: значения берутся из входа как есть."""
    specs: list[KeySpec] = [
        KeySpec(
            name="Производитель",
            value=product.manufacturer or NO_DATA,
            source="входные данные" if product.manufacturer else "нет данных",
        )
    ]
    for key, value in product.specs.items():
        specs.append(KeySpec(name=_capitalize(key), value=value, source="входные данные"))

    known = {normalize_text(k) for k in product.specs}
    empty_specs = [k for k in report.empty_specs if normalize_text(k) not in known]
    known |= {normalize_text(k) for k in empty_specs}
    invalid_ids = {id(s) for s in invalid}
    for spec in draft.extracted_specs:
        if id(spec) in invalid_ids or normalize_text(spec.name) in known:
            continue
        known.add(normalize_text(spec.name))
        specs.append(KeySpec(name=_capitalize(spec.name), value=spec.value.strip(), source="описание"))
    for key in empty_specs:
        specs.append(KeySpec(name=_capitalize(key), value=NO_DATA, source="нет данных"))

    names = " | ".join(normalize_text(s.name) for s in specs)
    for label, needles in TYPICAL_SPECS.items():
        if not any(n in names for n in needles):
            specs.append(KeySpec(name=label, value=NO_DATA, source="нет данных"))
    return specs


def _capitalize(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = normalize_text(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out
