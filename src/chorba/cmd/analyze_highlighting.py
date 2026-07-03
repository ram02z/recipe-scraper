import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DERIVED_PHRASE_WORDS = {
    "chips",
    "oil",
    "paste",
    "sauce",
    "broth",
    "stock",
    "juice",
    "milk",
    "powder",
    "crumbs",
    "leaves",
    "mix",
}
PREPARATION_EXTENSION_WORDS = {
    "cubes",
    "florets",
    "leaves",
    "pieces",
    "rounds",
    "slices",
    "wedges",
}
CONTEXTUAL_PREVIOUS_WORDS = {
    "fried",
    "baked",
    "pickled",
    "whipped",
}
GENERIC_SINGLE_WORD_ALIASES = {
    "cheese",
    "cream",
    "fat",
    "filling",
    "juice",
    "mix",
    "mixture",
    "oil",
    "pastry",
    "paste",
    "roast",
    "sauce",
    "seasoning",
    "soup",
    "stock",
    "water",
}
COMMON_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass
class HighlightIssue:
    category: str
    host: str
    url: str
    step_id: str
    step_text: str
    segment_text: str
    ingredient_id: str | None
    ingredient_names: list[str]
    previous_word: str | None
    next_word: str | None
    reason: str

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "host": self.host,
            "url": self.url,
            "step_id": self.step_id,
            "step_text": self.step_text,
            "segment_text": self.segment_text,
            "ingredient_id": self.ingredient_id,
            "ingredient_names": self.ingredient_names,
            "previous_word": self.previous_word,
            "next_word": self.next_word,
            "reason": self.reason,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze sampled recipe JSONL for highlighting quality issues."
    )
    parser.add_argument("input", type=Path, help="Input sampled recipe JSONL file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("highlight-analysis-report.json"),
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Maximum examples to keep per issue category.",
    )
    return parser.parse_args()


def tokenize_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", text.lower())


def ingredient_candidates(ingredient: dict) -> tuple[set[str], set[str], set[str]]:
    exact = set()
    multi = set()
    single = set()

    for name in ingredient.get("names", []):
        candidate = name.strip().lower()
        if not candidate:
            continue
        exact.add(candidate)

        words = candidate.split()
        if len(words) >= 3:
            multi.add(" ".join(words[-2:]))
        if len(words) >= 2:
            if words[-1] not in {
                "oil",
                "sauce",
                "paste",
                "milk",
                "juice",
                "broth",
                "stock",
                "water",
                "cream",
                "fat",
                "filling",
                "mixture",
                "seasoning",
            }:
                single.add(words[-1])

    return exact, multi, single


def classify_segment_match(segment_text: str, ingredient: dict) -> str:
    candidate = segment_text.strip().lower()
    exact, multi, single = ingredient_candidates(ingredient)
    if candidate in exact:
        return "exact_name"
    if candidate in multi:
        return "multi_word_alias"
    if candidate in single:
        return "single_word_alias"
    return "unknown"


def surrounding_words(
    step_text: str, start: int, end: int
) -> tuple[str | None, str | None]:
    before = tokenize_words(step_text[:start])
    after = tokenize_words(step_text[end:])
    previous_word = before[-1] if before else None
    next_word = after[0] if after else None
    return previous_word, next_word


def has_punctuation_boundary(step_text: str, start: int, end: int) -> bool:
    left = step_text[:start].rstrip()
    right = step_text[end:].lstrip()
    return bool(left and left[-1] in ",.;:") or bool(right and right[0] in ",.;:")


def detect_parser_name_issues(
    host: str, url: str, ingredient: dict
) -> list[HighlightIssue]:
    issues = []
    ingredient_id = ingredient["id"]
    names = ingredient.get("names", [])
    sentence = ingredient.get("sentence", "")
    for name in names:
        lowered = name.lower().strip()
        if not lowered:
            issues.append(
                HighlightIssue(
                    category="parser_empty_name",
                    host=host,
                    url=url,
                    step_id="",
                    step_text=sentence,
                    segment_text="",
                    ingredient_id=ingredient_id,
                    ingredient_names=names,
                    previous_word=None,
                    next_word=None,
                    reason="Ingredient contains an empty parsed name.",
                )
            )
        if lowered in {"combination", "juice", "lengthways"}:
            issues.append(
                HighlightIssue(
                    category="parser_suspicious_name",
                    host=host,
                    url=url,
                    step_id="",
                    step_text=sentence,
                    segment_text=lowered,
                    ingredient_id=ingredient_id,
                    ingredient_names=names,
                    previous_word=None,
                    next_word=None,
                    reason="Ingredient name looks like parsing noise rather than a usable ingredient reference.",
                )
            )
    return issues


def detect_segment_issues(
    host: str, url: str, step: dict, ingredient_lookup: dict[str, dict]
) -> tuple[list[HighlightIssue], Counter]:
    issues = []
    counters = Counter()

    for segment in step.get("segments", []):
        if segment.get("type") != "ingredient":
            continue

        ingredient = ingredient_lookup.get(segment["id"])
        if ingredient is None:
            continue

        match_type = classify_segment_match(segment["text"], ingredient)
        counters[f"match_type:{match_type}"] += 1

        previous_word, next_word = surrounding_words(
            step["text"], segment["start"], segment["end"]
        )

        if match_type == "single_word_alias":
            if next_word in DERIVED_PHRASE_WORDS and not has_punctuation_boundary(
                step["text"], segment["start"], segment["end"]
            ):
                issues.append(
                    HighlightIssue(
                        category="suspicious_single_word_alias",
                        host=host,
                        url=url,
                        step_id=step["id"],
                        step_text=step["text"],
                        segment_text=segment["text"],
                        ingredient_id=segment["id"],
                        ingredient_names=ingredient.get("names", []),
                        previous_word=previous_word,
                        next_word=next_word,
                        reason="Single-word alias is embedded in a likely derived phrase.",
                    )
                )
            elif (
                previous_word in CONTEXTUAL_PREVIOUS_WORDS
                and not has_punctuation_boundary(
                    step["text"], segment["start"], segment["end"]
                )
            ):
                issues.append(
                    HighlightIssue(
                        category="suspicious_single_word_alias",
                        host=host,
                        url=url,
                        step_id=step["id"],
                        step_text=step["text"],
                        segment_text=segment["text"],
                        ingredient_id=segment["id"],
                        ingredient_names=ingredient.get("names", []),
                        previous_word=previous_word,
                        next_word=next_word,
                        reason="Single-word alias is preceded by wording that often indicates a transformed ingredient phrase.",
                    )
                )

        if match_type == "unknown":
            issues.append(
                HighlightIssue(
                    category="unknown_match_type",
                    host=host,
                    url=url,
                    step_id=step["id"],
                    step_text=step["text"],
                    segment_text=segment["text"],
                    ingredient_id=segment["id"],
                    ingredient_names=ingredient.get("names", []),
                    previous_word=previous_word,
                    next_word=next_word,
                    reason="Ingredient segment did not map back to any exact name or derived alias candidate.",
                )
            )

    return issues, counters


def detect_missing_highlights(
    host: str, url: str, step: dict, ingredients: list[dict]
) -> list[HighlightIssue]:
    if any(segment.get("type") == "ingredient" for segment in step.get("segments", [])):
        return []

    step_text = step.get("text", "")
    lowered_step = step_text.lower()
    words = tokenize_words(step_text)
    issues = []

    for ingredient in ingredients:
        exact, multi, single = ingredient_candidates(ingredient)
        for candidate in sorted(exact | multi):
            if len(candidate.split()) < 2:
                continue
            if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", lowered_step):
                issues.append(
                    HighlightIssue(
                        category="missing_multi_word_match",
                        host=host,
                        url=url,
                        step_id=step["id"],
                        step_text=step_text,
                        segment_text=candidate,
                        ingredient_id=ingredient["id"],
                        ingredient_names=ingredient.get("names", []),
                        previous_word=None,
                        next_word=None,
                        reason="Direction contains a likely explicit multi-word ingredient mention but no highlight segments.",
                    )
                )
                return issues

        for candidate in sorted(single):
            if candidate in words and candidate not in COMMON_STOPWORDS:
                if candidate in GENERIC_SINGLE_WORD_ALIASES:
                    continue

                for index, word in enumerate(words):
                    if word != candidate:
                        continue
                    previous_word = words[index - 1] if index > 0 else None
                    next_word = words[index + 1] if index + 1 < len(words) else None
                    if previous_word in CONTEXTUAL_PREVIOUS_WORDS:
                        return []
                    if (
                        next_word in DERIVED_PHRASE_WORDS
                        and next_word not in PREPARATION_EXTENSION_WORDS
                    ):
                        return []
                issues.append(
                    HighlightIssue(
                        category="missing_single_word_match",
                        host=host,
                        url=url,
                        step_id=step["id"],
                        step_text=step_text,
                        segment_text=candidate,
                        ingredient_id=ingredient["id"],
                        ingredient_names=ingredient.get("names", []),
                        previous_word=None,
                        next_word=None,
                        reason="Direction contains a likely explicit single-word ingredient mention but no highlight segments.",
                    )
                )
                return issues

    return issues


def analyze_record(record: dict) -> tuple[list[HighlightIssue], Counter]:
    issues = []
    counters = Counter()
    host = record["host"]
    url = record["url"]
    recipe = record.get("recipe") or {}
    ingredients = recipe.get("ingredients", [])
    directions = recipe.get("directions", [])
    ingredient_lookup = {ingredient["id"]: ingredient for ingredient in ingredients}

    counters["recipes_analyzed"] += 1
    counters["ingredients_total"] += len(ingredients)
    counters["directions_total"] += len(directions)

    for ingredient in ingredients:
        issues.extend(detect_parser_name_issues(host, url, ingredient))

    for step in directions:
        counters["steps_total"] += 1
        segment_issues, segment_counts = detect_segment_issues(
            host, url, step, ingredient_lookup
        )
        issues.extend(segment_issues)
        counters.update(segment_counts)

        ingredient_segment_count = sum(
            1
            for segment in step.get("segments", [])
            if segment.get("type") == "ingredient"
        )
        if ingredient_segment_count == 0:
            counters["steps_without_matches"] += 1

        issues.extend(detect_missing_highlights(host, url, step, ingredients))

    return issues, counters


def trim_issue_samples(
    issues: list[HighlightIssue], sample_limit: int
) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        bucket = grouped[issue.category]
        if len(bucket) < sample_limit:
            bucket.append(issue.as_dict())
    return dict(grouped)


def main() -> None:
    args = parse_args()
    records = []
    with args.input.open("r", encoding="utf-8") as input_file:
        for line in input_file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not record.get("scrape_ok") or not record.get("recipe_found"):
                continue
            records.append(record)

    aggregate_counts = Counter()
    issues = []
    host_counts = Counter()

    for record in records:
        host_counts[record["host"]] += 1
        record_issues, record_counts = analyze_record(record)
        issues.extend(record_issues)
        aggregate_counts.update(record_counts)

    issue_counts = Counter(issue.category for issue in issues)

    report = {
        "input": str(args.input),
        "recipes_analyzed": len(records),
        "hosts": dict(sorted(host_counts.items())),
        "counts": dict(aggregate_counts),
        "issue_counts": dict(issue_counts),
        "issue_samples": trim_issue_samples(issues, args.sample_limit),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"recipes_analyzed={len(records)}")
    print(f"hosts={dict(sorted(host_counts.items()))}")
    print(f"issue_counts={dict(issue_counts)}")
    print(f"report={args.output}")


if __name__ == "__main__":
    main()
