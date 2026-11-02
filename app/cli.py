"""Командная строка.

    python -m app generate examples/inputs/products.json --format md --out out/
    python -m app generate product.json --dry-run      # показать промпт без вызова LLM
    cat product.json | python -m app generate -         # чтение из stdin
    python -m app serve --port 8000                     # веб-форма
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from .config import ConfigError, Settings
from .input_validation import InputError, load_json, parse_many, parse_product
from .llm import LLMError, make_client
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .render import card_to_markdown
from .service import generate_card

EXIT_INPUT, EXIT_LLM, EXIT_CONFIG = 1, 2, 3


_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
        "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
        "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)


def _slug(text: str) -> str:
    """ASCII-имя файла из названия товара."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(_TRANSLIT)).strip("-")
    return slug[:60].rstrip("-") or "product"


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise InputError(f"Файл не найден: {path}") from None
    except UnicodeDecodeError:
        raise InputError(f"Файл {path} не в кодировке UTF-8.") from None


def _print_input_error(exc: InputError, prefix: str = "") -> None:
    print(f"{prefix}Ошибка входных данных: {exc.message}", file=sys.stderr)
    for d in exc.details:
        print(f"  - {d}", file=sys.stderr)


def cmd_generate(args: argparse.Namespace) -> int:
    try:
        items = parse_many(load_json(_read_input(args.input)))
    except InputError as exc:
        _print_input_error(exc)
        return EXIT_INPUT

    client = None
    if not args.dry_run:
        try:
            settings = Settings.from_env()
            client = make_client(settings)
        except ConfigError as exc:
            print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
            return EXIT_CONFIG

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for idx, item in enumerate(items, start=1):
        prefix = f"[{idx}/{len(items)}] " if len(items) > 1 else ""
        try:
            product, report = parse_product(item)
        except InputError as exc:
            _print_input_error(exc, prefix)
            exit_code = exit_code or EXIT_INPUT
            continue

        if args.dry_run:
            print(f"{prefix}=== SYSTEM ===\n{SYSTEM_PROMPT}\n=== USER ===\n{build_user_prompt(product, report)}\n")
            continue

        print(f"{prefix}Генерация: {product.name} …", file=sys.stderr)
        try:
            card = generate_card(product, report, client, max_attempts=settings.max_attempts)
        except LLMError as exc:
            print(f"{prefix}Ошибка LLM: {exc}", file=sys.stderr)
            exit_code = exit_code or EXIT_LLM
            continue

        markdown = card_to_markdown(card)
        as_json = json.dumps(card.model_dump(), ensure_ascii=False, indent=2)
        if out_dir:
            stem = out_dir / f"{idx:02d}-{_slug(product.name)}"
            if args.format in ("md", "both"):
                stem.with_suffix(".md").write_text(markdown, encoding="utf-8")
            if args.format in ("json", "both"):
                stem.with_suffix(".json").write_text(as_json + "\n", encoding="utf-8")
            print(f"{prefix}Сохранено: {stem}.*  (статус: {card.status})", file=sys.stderr)
        else:
            print(markdown if args.format == "md" else as_json)
            if args.format == "both":
                print(markdown)
    return exit_code


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("app.web:app", host=args.host, port=args.port, reload=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="Черновики карточек товаров КИП через LLM.")
    parser.add_argument("-v", "--verbose", action="store_true", help="подробный лог (попытки, проверки)")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="сгенерировать карточку(и) из JSON")
    gen.add_argument("input", help="путь к JSON (объект или список товаров) или - для stdin")
    gen.add_argument("-f", "--format", choices=["md", "json", "both"], default="md")
    gen.add_argument("-o", "--out", help="каталог для сохранения результатов")
    gen.add_argument("--dry-run", action="store_true", help="только проверить вход и показать промпт")
    gen.set_defaults(func=cmd_generate)

    srv = sub.add_parser("serve", help="запустить веб-форму")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    srv.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)
