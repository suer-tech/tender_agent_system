"""Запуск агента Bicotender из консоли.

Использование:
    python run_bicotender.py                           # все ключи из config.yaml
    python run_bicotender.py "внедрение ИИ"            # свой запрос
    python run_bicotender.py "чат-бот" --limit 5       # ограничить кол-во
    python run_bicotender.py "ML" --no-headless         # с окном браузера
"""
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.agents import bicotender_agent


def main():
    parser = argparse.ArgumentParser(description="Bicotender deep search agent")
    parser.add_argument("query", nargs="?", default=None, help="Поисковый запрос")
    parser.add_argument("--keywords", nargs="+", help="Ключевые слова (по умолчанию из config.yaml)")
    parser.add_argument("--limit", type=int, default=10, help="Макс. тендеров на ключ (default: 10)")
    parser.add_argument("--max-docs", type=int, default=5, help="Макс. документов на тендер (default: 5)")
    parser.add_argument("--no-headless", action="store_true", help="Показать окно браузера")
    parser.add_argument("--output", type=str, help="Сохранить отчёт в файл")
    args = parser.parse_args()

    user_query = args.query or "Внедрение искусственного интеллекта, ML, автоматизация бизнес-процессов"
    keywords = args.keywords  # None → агент возьмёт из config.yaml

    print(f"{'=' * 60}")
    print(f"Bicotender Deep Search Agent")
    print(f"Запрос: {user_query}")
    print(f"Лимит: {args.limit} | Документов: {args.max_docs}")
    print(f"{'=' * 60}\n")

    result = bicotender_agent.run(
        user_query=user_query,
        keywords=keywords,
        limit=args.limit,
        headless=not args.no_headless,
        max_docs=args.max_docs,
    )

    print(f"\n{'=' * 60}")
    print(f"РЕЗУЛЬТАТЫ")
    print(f"{'=' * 60}")
    print(f"Найдено: {result['total_found']}")
    print(f"Проанализировано: {result['analyzed']}")
    print(f"Релевантных: {result['relevant_count']}")
    print(f"{'=' * 60}\n")

    print("ОТЧЁТ:")
    print(result["report"])

    # Сохранение
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(result["report"], encoding="utf-8")
        print(f"\nОтчёт сохранён: {out_path}")
    else:
        default_out = ROOT / "bicotender_report.md"
        default_out.write_text(result["report"], encoding="utf-8")
        print(f"\nОтчёт сохранён: {default_out}")


if __name__ == "__main__":
    main()
