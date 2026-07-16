#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from sklearn.metrics import accuracy_score, cohen_kappa_score
from gladiators.agent.llm import AnthropicLLMClient, FakeLLMClient, GeminiLLMClient, GroqLLMClient, HuggingFaceLLMClient

ap=argparse.ArgumentParser(); ap.add_argument("--provider", choices=["fake","anthropic","gemini","huggingface","groq"], default="fake"); ap.add_argument("--fixture", default="eval/judge_reliability.json"); args=ap.parse_args()
client = FakeLLMClient() if args.provider == "fake" else GeminiLLMClient() if args.provider == "gemini" else HuggingFaceLLMClient() if args.provider == "huggingface" else GroqLLMClient() if args.provider == "groq" else AnthropicLLMClient()
items=json.loads(Path(args.fixture).read_text()); human=[x["human_score"] for x in items]; judged=[client.judge(x["answer"], x["rubric"])["score"] for x in items]
print(json.dumps({"provider":client.provider,"model":client.model,"prompt_version":client.prompt_version,"n":len(items),"accuracy":accuracy_score(human,judged),"cohen_kappa":cohen_kappa_score(human,judged)}, indent=2))
