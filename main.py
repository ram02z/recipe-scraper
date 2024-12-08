from recipe_scrapers import scrape_html
import httpx
from ingredient_parser import parse_ingredient
from robots import RobotFileManager

from sitemap import SitemapParserFactory
import asyncio

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0"
)


async def main():
    url = "https://www.tasty.co"
    robot_file_manager = RobotFileManager(url)
    if (sitemap := robot_file_manager.sitemap) is None:
        raise RuntimeError(f"No sitemap found for url: {url}")
    print(sitemap)
    sitemap_parser = SitemapParserFactory.from_xml_url(sitemap)
    print(type(sitemap_parser))
    sitemap_parser.user_agent = USER_AGENT
    recipe_urls = await sitemap_parser.get_recipe_urls()
    print(len(recipe_urls))
    print(len(robot_file_manager.filter_urls(recipe_urls)))
    url = recipe_urls[0]
    print(url)
    html = httpx.get(url, headers={"User-Agent": USER_AGENT}).text
    scraper = scrape_html(html, org_url=url)
    ingredients = scraper.ingredients()
    parsed_ingredients = [
        food.text
        for i in ingredients
        for food in parse_ingredient(i, foundation_foods=True).foundation_foods
    ]
    print(ingredients)
    print(parsed_ingredients)


if __name__ == "__main__":
    asyncio.run(main())
