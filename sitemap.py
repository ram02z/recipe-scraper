import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests


class BaseSitemapParser:
    def __init__(self, xml_url: str) -> None:
        self.xml_url = xml_url

    def is_valid_recipe_path(self, path: str) -> bool:
        raise NotImplementedError()

    @staticmethod
    def _get_domain_names() -> list[str]:
        raise NotImplementedError()

    def get_recipe_urls(self) -> list[str]:
        r = requests.get(self.xml_url)
        xml = r.text
        soup = BeautifulSoup(xml, features="lxml")

        urls = []
        for url in soup.findAll("loc"):
            url = url.getText("", True)
            parsed_url = urlparse(url)
            path = parsed_url.path
            if self.is_valid_recipe_path(path):
                urls.append(url)

        return urls


class GenericSitemapParser(BaseSitemapParser):
    @staticmethod
    def _get_domain_names() -> list[str]:
        return []

    def is_valid_recipe_path(self, path: str) -> bool:
        return path != ""


class BBCSitemapParser(BaseSitemapParser):
    RECIPE_PATH_PATTERN = r"^(.*)_(\d+)$"

    @staticmethod
    def _get_domain_names() -> list[str]:
        return ["www.bbc.co.uk"]

    def is_valid_recipe_path(self, path: str) -> bool:
        path_parts = path.strip("/").split("/")
        return bool(re.search(self.RECIPE_PATH_PATTERN, path_parts[-1]))

class TastySitemapParser(BaseSitemapParser):
    @staticmethod
    def _get_domain_names() -> list[str]:
        return ["www.tasty.co"]

    def is_valid_recipe_path(self, path: str) -> bool:
        path_parts = path.strip("/").split("/")
        return "recipe" in path_parts


class SitemapParserFactory:
    @staticmethod
    def from_xml_url(url: str):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        parser_map = {
            domain: parser_class
            for parser_class in BaseSitemapParser.__subclasses__()
            for domain in parser_class._get_domain_names()
        }

        parser_class = parser_map.get(domain, GenericSitemapParser)

        return parser_class(url)
