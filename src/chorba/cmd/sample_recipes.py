import argparse
import asyncio
import json
import random
import time
from pathlib import Path
from dataclasses import dataclass

from curl_cffi import requests
from pydantic import TypeAdapter

from chorba.lib.markup._schema_org import Recipe, ensure_ingredient_parser_ready
from chorba.lib.markup.scraper import RecipeScraper
from chorba.lib.robot import RobotFileManager
from chorba.lib.sitemap import SitemapParserFactory


recipe_adapter = TypeAdapter(Recipe)
HOST_SEED_URLS = {
    "bbc.co.uk": "https://www.bbc.co.uk/food",
}


def get_supported_hosts() -> list[str]:
    return sorted(SitemapParserFactory.SITEMAPS.keys())


def seed_url_for_host(host: str) -> str:
    if host in HOST_SEED_URLS:
        return HOST_SEED_URLS[host]
    if host.startswith("www."):
        return f"https://{host}/"
    return f"https://www.{host}/"


def sitemap_candidates_for_host(host: str) -> list[str]:
    candidates = []
    seed_url = seed_url_for_host(host).rstrip("/")
    candidates.append(f"{seed_url}/sitemap.xml")

    if host.startswith("www."):
        candidates.append(f"https://{host}/sitemap.xml")
    else:
        candidates.append(f"https://{host}/sitemap.xml")
        candidates.append(f"https://www.{host}/sitemap.xml")

    return dedupe_urls(candidates)


def resolve_sitemap_url(host: str) -> tuple[str | None, int]:
    robot = RobotFileManager(seed_url_for_host(host))
    if robot.sitemap:
        return robot.sitemap, robot.crawl_delay

    for sitemap_url in sitemap_candidates_for_host(host):
        try:
            response = requests.get(sitemap_url, impersonate="chrome", timeout=30)
            response.raise_for_status()
        except Exception:
            continue
        return sitemap_url, robot.crawl_delay

    return None, robot.crawl_delay


def dedupe_urls(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))


def sample_urls(urls: list[str], per_site: int, rng: random.Random) -> list[str]:
    if per_site <= 0 or len(urls) <= per_site:
        return list(urls)
    return rng.sample(urls, per_site)


def serialize_recipe(recipe: Recipe | None) -> dict | None:
    if recipe is None:
        return None
    return recipe_adapter.dump_python(recipe, mode="json")


def parse_hosts(hosts: str | None) -> list[str]:
    if not hosts:
        return get_supported_hosts()
    return [host.strip() for host in hosts.split(",") if host.strip()]


async def discover_recipe_urls(host: str) -> tuple[str | None, int, list[str]]:
    robot = RobotFileManager(seed_url_for_host(host))
    sitemap, crawl_delay = resolve_sitemap_url(host)
    if not sitemap:
        return None, crawl_delay, []

    parser = SitemapParserFactory.from_xml_url(sitemap)
    urls = await parser.get_recipe_urls()
    urls = dedupe_urls(robot.filter_urls(urls))

    return sitemap, crawl_delay, urls


def build_record(
    *,
    host: str,
    sitemap: str,
    crawl_delay: int,
    seed: int,
    sample_index: int,
    url: str,
    recipe: Recipe | None,
    error: str | None,
) -> dict:
    return {
        "host": host,
        "sitemap": sitemap,
        "crawl_delay": crawl_delay,
        "seed": seed,
        "sample_index": sample_index,
        "url": url,
        "scrape_ok": error is None,
        "recipe_found": recipe is not None,
        "error": error,
        "recipe": serialize_recipe(recipe),
    }


@dataclass
class HostSamplingResult:
    host: str
    sitemap: str | None
    crawl_delay: int
    discovered_urls: int
    sampled_urls: int
    skipped: bool
    records: list[dict]
    discovery_error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sample recipe URLs from supported sitemaps and dump scraped results as JSONL."
    )
    parser.add_argument(
        "--per-site",
        type=int,
        default=10,
        help="Number of recipe URLs to sample per site.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used for reproducible sampling.",
    )
    parser.add_argument(
        "--hosts",
        type=str,
        default=None,
        help="Comma-separated host allowlist. Defaults to all supported hosts.",
    )
    parser.add_argument(
        "--max-sites",
        type=int,
        default=None,
        help="Optional cap on the number of hosts to process.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sampled-recipes.jsonl"),
        help="JSONL output path.",
    )
    parser.add_argument(
        "--host-concurrency",
        type=int,
        default=4,
        help="Maximum number of hosts to process in parallel.",
    )
    return parser.parse_args()


async def sample_host(
    host: str,
    *,
    per_site: int,
    seed: int,
    semaphore: asyncio.Semaphore,
) -> HostSamplingResult:
    async with semaphore:
        try:
            sitemap, crawl_delay, urls = await discover_recipe_urls(host)
        except Exception as exc:
            print(f"{host}: skipped during discovery ({exc})")
            return HostSamplingResult(
                host=host,
                sitemap=None,
                crawl_delay=0,
                discovered_urls=0,
                sampled_urls=0,
                skipped=True,
                records=[],
                discovery_error=str(exc),
            )

        if not sitemap:
            print(f"{host}: skipped (no sitemap found)")
            return HostSamplingResult(
                host=host,
                sitemap=None,
                crawl_delay=crawl_delay,
                discovered_urls=0,
                sampled_urls=0,
                skipped=True,
                records=[],
                discovery_error=None,
            )

        rng = random.Random(f"{seed}:{host}")
        sampled = sample_urls(urls, per_site, rng)
        print(
            f"{host}: sitemap={sitemap} discovered={len(urls)} sampled={len(sampled)} crawl_delay={crawl_delay}"
        )

        scraper = RecipeScraper()
        records = []
        for sample_index, url in enumerate(sampled):
            recipe = None
            error = None

            try:
                recipe = await asyncio.to_thread(scraper.scrape_from_url, url)
            except Exception as exc:
                error = str(exc)

            records.append(
                build_record(
                    host=host,
                    sitemap=sitemap,
                    crawl_delay=crawl_delay,
                    seed=seed,
                    sample_index=sample_index,
                    url=url,
                    recipe=recipe,
                    error=error,
                )
            )

            if crawl_delay > 0 and sample_index < len(sampled) - 1:
                await asyncio.sleep(crawl_delay)

        return HostSamplingResult(
            host=host,
            sitemap=sitemap,
            crawl_delay=crawl_delay,
            discovered_urls=len(urls),
            sampled_urls=len(sampled),
            skipped=False,
            records=records,
            discovery_error=None,
        )


async def run_sampling(args: argparse.Namespace) -> list[HostSamplingResult]:
    ensure_ingredient_parser_ready()

    hosts = parse_hosts(args.hosts)
    if args.max_sites is not None:
        hosts = hosts[: args.max_sites]

    semaphore = asyncio.Semaphore(max(args.host_concurrency, 1))
    tasks = [
        sample_host(host, per_site=args.per_site, seed=args.seed, semaphore=semaphore)
        for host in hosts
    ]
    return await asyncio.gather(*tasks)


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    results = asyncio.run(run_sampling(args))

    attempted_hosts = len(results)
    skipped_hosts = sum(1 for result in results if result.skipped)
    discovered_urls = sum(result.discovered_urls for result in results)
    sampled_urls = sum(result.sampled_urls for result in results)
    recipes_found = sum(
        1 for result in results for record in result.records if record["recipe_found"]
    )
    scrape_failures = sum(
        1 for result in results for record in result.records if not record["scrape_ok"]
    )

    with args.output.open("w", encoding="utf-8") as output_file:
        for result in results:
            for record in result.records:
                output_file.write(json.dumps(record, ensure_ascii=True) + "\n")

    print(
        "Summary: "
        f"attempted_hosts={attempted_hosts} skipped_hosts={skipped_hosts} "
        f"discovered_urls={discovered_urls} sampled_urls={sampled_urls} "
        f"recipes_found={recipes_found} scrape_failures={scrape_failures} output={args.output}"
    )


if __name__ == "__main__":
    main()
