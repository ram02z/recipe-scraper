from recipe_scrapers import _abstract, scrape_html
import requests
from ingredient_parser import parse_ingredient

from sitemap import SitemapParserFactory

headers = _abstract.HEADERS


def main():
    sitemap_parser = SitemapParserFactory.from_xml_url(
        "https://www.tasty.co/sitemaps/tasty/sitemap.xml"
    )
    recipe_urls = sitemap_parser.get_recipe_urls()
    print(recipe_urls)
    url = recipe_urls[0]
    html = requests.get(url, headers=headers).content
    scraper = scrape_html(html, org_url=url)
    ingredients = scraper.ingredients()
    parsed_ingredients = [
        food.text
        for i in ingredients
        for food in parse_ingredient(i, foundation_foods=True).foundation_foods
    ]
    print(parsed_ingredients)


if __name__ == "__main__":
    main()
