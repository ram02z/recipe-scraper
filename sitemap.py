import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import logging
import httpx
import asyncio


class BaseSitemapParser:
    recipe_path_pattern: str = ""

    def __init__(self, xml_url: str, max_depth: int = 3, timeout: int = 60) -> None:
        self._user_agent = None
        self.xml_url = xml_url
        self.max_depth = max_depth
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    def _is_valid_recipe_path(self, path: str) -> bool:
        return bool(re.search(self.recipe_path_pattern, path))

    @staticmethod
    def host() -> str:
        raise NotImplementedError()

    @property
    def user_agent(self) -> str | None:
        return self._user_agent

    @user_agent.setter
    def user_agent(self, val: str):
        self._user_agent = val

    async def _fetch_xml(self, url: str, client: httpx.AsyncClient) -> str | None:
        try:
            headers = {
                "Accept": "application/xml, text/xml",
                "Accept-Encoding": "gzip, deflate, br",
            }
            if self.user_agent:
                headers["User-Agent"] = self.user_agent
            response = await client.get(
                url,
                timeout=self.timeout,
                headers=headers,
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            self.logger.error(f"Error while requesting {exc.request.url!r}.")
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

                    if self._is_valid_recipe_path(path):
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
    recipe_path_pattern = "^(.*)$"


class BBCSitemapParser(BaseSitemapParser):
    recipe_path_pattern = r"^(.*)/recipes/(.*)_(\d+)$"

    @staticmethod
    def host() -> str:
        return "bbc.co.uk"


class TastySitemapParser(BaseSitemapParser):
    recipe_path_pattern = r"^(.*)/recipe/(.*)$"

    @staticmethod
    def host() -> str:
        return "tasty.co"


class AllRecipesSitemapParser(BaseSitemapParser):
    recipe_path_pattern = r"^(.*)-recipe-(\d+)$|^(.*)/recipe/(\d+)/(.*)$"

    @staticmethod
    def host() -> str:
        return "allrecipes.com"


class BonApetitSitemapParser(BaseSitemapParser):
    recipe_path_pattern = r"^/recipe/(.*)$"

    @staticmethod
    def host() -> str:
        return "bonappetit.com"


class EpicuriousSitemapParser(BaseSitemapParser):
    recipe_path_pattern = r"^/recipes/food/(.*)$"

    @staticmethod
    def host() -> str:
        return "epicurious.com"


class BBCGoodFoodSitemapParser(BaseSitemapParser):
    recipe_path_pattern = (
        r"^/(premium|recipes)/(?!.*recipes$)[a-z]+(-[a-z]+){0,7}$"
    )

    @staticmethod
    def host() -> str:
        return "bbcgoodfood.com"


class SitemapParserFactory:
    SITEMAPS = {
        BBCSitemapParser.host(): BBCSitemapParser,
        TastySitemapParser.host(): TastySitemapParser,
        AllRecipesSitemapParser.host(): AllRecipesSitemapParser,
        BonApetitSitemapParser.host(): BonApetitSitemapParser,
        EpicuriousSitemapParser.host(): EpicuriousSitemapParser,
        BBCGoodFoodSitemapParser.host(): BBCGoodFoodSitemapParser,
    }

    @classmethod
    def from_xml_url(cls, url: str) -> BaseSitemapParser:
        domain = urlparse(url).netloc.lower()
        domain = domain.split("www.")[1] if domain.startswith("www.") else domain

        parser_class = cls.SITEMAPS.get(domain, GenericSitemapParser)

        return parser_class(url)
