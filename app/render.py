"""Представление карточки в Markdown — для копирования в CMS/документ."""

from __future__ import annotations

from .schemas import SEO_DESCRIPTION_MAX, SEO_DESCRIPTION_MIN, SEO_TITLE_MAX, ProductCard


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def card_to_markdown(card: ProductCard) -> str:
    status = "✅ готово к вычитке" if card.status == "ok" else "⚠️ требует проверки"
    lines = [
        f"# {card.product_name}",
        "",
        f"Статус: **{status}**",
        "",
        f"## SEO-заголовок ({card.seo_title_length}/{SEO_TITLE_MAX} симв.)",
        "",
        card.seo_title,
        "",
        f"## SEO-описание ({card.seo_description_length} симв., норма "
        f"{SEO_DESCRIPTION_MIN}–{SEO_DESCRIPTION_MAX})",
        "",
        card.seo_description,
        "",
        "## Ключевые характеристики",
        "",
        "| Характеристика | Значение | Источник |",
        "|---|---|---|",
    ]
    for spec in card.key_specs:
        lines.append(f"| {_md_cell(spec.name)} | {_md_cell(spec.value)} | {spec.source} |")

    lines += ["", "## Поисковые запросы", ""]
    lines += [f"- {q}" for q in card.search_queries]

    lines += ["", "## Для менеджера", "", "**Кому подходит:**", ""]
    lines += [f"- {a}" for a in card.commercial.audience] or ["- данных нет"]
    lines += ["", "**Какие задачи решает:**", ""]
    lines += [f"- {t}" for t in card.commercial.tasks] or ["- данных нет"]

    if card.needs_clarification:
        lines += ["", "## Требует уточнения", ""]
        lines += [f"- {c}" for c in card.needs_clarification]

    if card.warnings:
        lines += ["", "## Замечания автоматической проверки", ""]
        lines += [f"- {w}" for w in card.warnings]

    lines += [
        "",
        "---",
        f"_Черновик сгенерирован: {card.meta.provider} / {card.meta.model}, "
        f"попыток: {card.meta.attempts}. Перед публикацией проверьте текст._",
        "",
    ]
    return "\n".join(lines)
