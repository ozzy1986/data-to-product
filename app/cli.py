"""Генерация из консоли, без веб-сервера.

  python -m app.cli examples/input/dm02.json                 — Markdown в консоль
  python -m app.cli examples/input/*.json --out examples/output  — <имя>.json и <имя>.md в папку
  python -m app.cli product.json --json                      — JSON в консоль
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import settings
from .factory import build_generator
from .llm import LLMError
from .parsing import ApiError, parse_product


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli", description="Черновик карточки товара по JSON прибора")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, help="папка для <имя>.json и <имя>.md")
    ap.add_argument("--json", action="store_true", help="печатать JSON вместо Markdown")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # консоль Windows по умолчанию cp1251
        stream.reconfigure(encoding="utf-8")

    generator = build_generator(settings)
    failed = 0
    for path in args.files:
        try:
            product = parse_product(path.read_bytes())
            result = generator.generate(product)
        except ApiError as e:
            print(f"{path}: {e.message}", *e.details, sep="\n  ", file=sys.stderr)
            failed += 1
            continue
        except (OSError, LLMError) as e:
            print(f"{path}: {e}", file=sys.stderr)
            failed += 1
            continue
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            record = {"id": path.stem, "input": product.model_dump(), "result": result.model_dump()}
            (args.out / f"{path.stem}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (args.out / f"{path.stem}.md").write_text(result.markdown, encoding="utf-8")
            print(f"{path} → {args.out / path.stem}.{{json,md}} (попыток: {result.attempts}, "
                  f"предупреждений: {len(result.warnings)})")
        else:
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2) if args.json else result.markdown)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
