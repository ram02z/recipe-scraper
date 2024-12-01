import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import logging
import httpx
import asyncio


class BaseSitemapParser:
    def __init__(self, xml_url: str, max_depth: int = 3, timeout: int = 10) -> None:
        self.xml_url = xml_url
        self.max_depth = max_depth
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    def is_valid_recipe_path(self, path: str) -> bool:
        raise NotImplementedError()

    @staticmethod
    def host() -> str:
        raise NotImplementedError()

    async def _fetch_xml(self, url: str, client: httpx.AsyncClient) -> str | None:
        try:
            response = await client.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0",
                    "Accept": "application/xml, text/xml",
                    "Accept-Encoding": "gzip, deflate, br",
                },
            )
            response.raise_for_status()
            return response.text
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            self.logger.error(f"Error fetching {url}: {e}")
            return None

    def _parse_sitemap_urls(
        self, xml: str, base_url: str
    ) -> tuple[list[str], list[str]]:
        soup = BeautifulSoup(xml, "lxml-xml")

        sitemap_entries = soup.findAll(["sitemap", "url"])

        urls = []
        subsitemap_urls = []

        for entry in sitemap_entries:
            if entry.name == "sitemap":
                loc = entry.find("loc")
                if loc:
                    subsitemap_url = loc.getText("", True)
                    subsitemap_urls.append(urljoin(base_url, subsitemap_url))
            else:
                loc = entry.find("loc")
                if loc:
                    url = loc.getText("", True)
                    parsed_url = urlparse(url)
                    path = parsed_url.path

                    if self.is_valid_recipe_path(path):
                        urls.append(url)

        return urls, subsitemap_urls

    async def _process_sitemap(
        self, url: str, client: httpx.AsyncClient, current_depth: int = 0
    ) -> list[str]:
        if current_depth >= self.max_depth:
            self.logger.warning(f"Max depth reached for {url}")
            return []

        xml = await self._fetch_xml(url, client)
        if not xml:
            return []

        urls, subsitemap_urls = self._parse_sitemap_urls(xml, url)

        if subsitemap_urls:
            subsitemap_tasks = [
                self._process_subsitemap(subsitemap_url, client, current_depth)
                for subsitemap_url in subsitemap_urls
            ]
            subsitemap_results = await asyncio.gather(*subsitemap_tasks)

            for result in subsitemap_results:
                urls.extend(result)

        return urls

    async def _process_subsitemap(
        self, subsitemap_url: str, client: httpx.AsyncClient, current_depth: int
    ) -> list[str]:
        subsitemap_parser = SitemapParserFactory.from_xml_url(subsitemap_url)

        return await subsitemap_parser._process_sitemap(
            subsitemap_url, client, current_depth + 1
        )

    async def get_recipe_urls(self) -> list[str]:
        async with httpx.AsyncClient() as client:
            return await self._process_sitemap(self.xml_url, client)


class GenericSitemapParser(BaseSitemapParser):
    def is_valid_recipe_path(self, path: str) -> bool:
        return path != ""


class BBCSitemapParser(BaseSitemapParser):
    RECIPE_PATH_PATTERN = r"^(.*)_(\d+)$"

    @staticmethod
    def host() -> str:
        return "www.bbc.co.uk"

    def is_valid_recipe_path(self, path: str) -> bool:
        path_parts = path.strip("/").split("/")
        return "recipes" in path_parts and bool(
            re.search(self.RECIPE_PATH_PATTERN, path_parts[-1])
        )


class TastySitemapParser(BaseSitemapParser):
    @staticmethod
    def host() -> str:
        return "www.tasty.co"

    def is_valid_recipe_path(self, path: str) -> bool:
        path_parts = path.strip("/").split("/")
        return "recipe" in path_parts


class AllRecipesSitemapParser(BaseSitemapParser):
    RECIPE_PATH_PATTERN = r"^(.*)-recipe-(\d+)$"

    @staticmethod
    def host() -> str:
        return "www.allrecipes.com"

    def is_valid_recipe_path(self, path: str) -> bool:
        path_parts = path.strip("/").split("/")
        return "recipe" in path_parts or bool(
            re.search(self.RECIPE_PATH_PATTERN, path_parts[-1])
        )


class BonApetitSitemapParser(BaseSitemapParser):
    @staticmethod
    def host() -> str:
        return "www.bonappetit.com"

    def is_valid_recipe_path(self, path: str) -> bool:
        path_parts = path.strip("/").split("/")
        return "recipe" in path_parts


class SitemapParserFactory:
    SITEMAPS = {
        BBCSitemapParser.host(): BBCSitemapParser,
        TastySitemapParser.host(): TastySitemapParser,
        AllRecipesSitemapParser.host(): AllRecipesSitemapParser,
        BonApetitSitemapParser.host(): BonApetitSitemapParser,
    }

    @classmethod
    def from_xml_url(cls, url: str) -> BaseSitemapParser:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        parser_class = cls.SITEMAPS.get(domain, GenericSitemapParser)

        return parser_class(url)
