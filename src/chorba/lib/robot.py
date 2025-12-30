from urllib.parse import urljoin, urlparse
from robots.robotparser import RobotFileParser


class RobotFileManager:
    rp: RobotFileParser

    def __init__(self, url: str):
        self.og_url = url
        parsed_url = urlparse(url)
        self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        self.path = parsed_url.path
        robots_url = urljoin(self.base_url, "/robots.txt")

        self.rp = RobotFileParser(robots_url)
        self.rp.read()

    @property
    def sitemap(self) -> str | None:
        rp_site_maps = self.rp.site_maps()
        if not rp_site_maps:
            return None

        if self.path:
            for sm_url in rp_site_maps:
                parsed_sm_url = urlparse(sm_url)
                if sm_url.startswith(self.og_url):
                    return sm_url

        for sm_url in rp_site_maps:
            parsed_sm_url = urlparse(sm_url)
            if parsed_sm_url.path == "/sitemap.xml":
                return sm_url

        return rp_site_maps[0]

    @property
    def crawl_delay(self) -> int:
        rp_crawl_delay = self.rp.crawl_delay("*")

        if rp_crawl_delay is None:
            return 0
        return int(rp_crawl_delay)

    def filter_urls(self, urls: list[str]) -> list[str]:
        return [url for url in urls if self.rp.can_fetch("*", url)]
