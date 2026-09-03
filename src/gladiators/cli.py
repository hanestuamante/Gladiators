from __future__ import annotations

import argparse
import json

from gladiators.runtime_factory import create_runtime


def main() -> None:
    parser = argparse.ArgumentParser(description="Gladiators verified analytics agent")
    parser.add_argument("question"); parser.add_argument("--provider", choices=["offline", "gemini", "huggingface", "groq"], default="offline"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(); response = create_runtime(args.provider).run(args.question)
    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2) if args.json else response.answer)


if __name__ == "__main__": main()
