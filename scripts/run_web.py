"""Запуск веб-интерфейса TenderAI.

Использование:
    python scripts/run_web.py                # http://localhost:8000
    python scripts/run_web.py --port 3000    # http://localhost:3000
    python scripts/run_web.py --host 0.0.0.0 # доступ по сети
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="TenderAI Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    args = parser.parse_args()

    print(f"\n  TenderAI Web Interface")
    print(f"  http://{args.host}:{args.port}\n")

    uvicorn.run(
        "apps.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
