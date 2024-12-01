from recipe_scrapers import _abstract, scrape_html
import httpx
from ingredient_parser import parse_ingredient

from sitemap import SitemapParserFactory
import asyncio

headers = _abstract.HEADERS


async def main():
    sitemap_parser = SitemapParserFactory.from_xml_url(
        "https://www.bonappetit.com/sitemap.xml"
    )
    recipe_urls = await sitemap_parser.get_recipe_urls()
    print(len(recipe_urls))
    url = recipe_urls[0]
    html = httpx.get(url, headers=headers).text
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
