import logging
import re
from typing import Optional, List
import requests
from bs4 import BeautifulSoup

from models import (
    ParseRecipeRequest,
    ParseRecipeResponse,
    ParsedIngredient,
    ParseIngredientRequest,
    Effort
)
from ingredient_service import IngredientService

logger = logging.getLogger(__name__)


class RecipeService:
    def __init__(self):
        self.ingredient_service = IngredientService()

    def parse_recipe(self, request: ParseRecipeRequest) -> ParseRecipeResponse:
        """
        Parse a recipe from a URL.
        First tries to extract OpenGraph metadata, then falls back to HTML parsing.
        """
        logger.info(f"Parsing recipe from URL: {request.url}")

        try:
            # Fetch the webpage
            html_content = self._fetch_url(request.url)

            # Parse HTML
            soup = BeautifulSoup(html_content, 'lxml')

            # Extract data using multiple methods
            title = self._extract_title(soup)
            description = self._extract_description(soup)
            total_time_minutes = self._extract_time(soup)
            ingredients_raw = self._extract_ingredients(soup)

            # Parse ingredients using ingredient service
            ingredients = []
            for raw_ingredient in ingredients_raw:
                try:
                    parse_request = ParseIngredientRequest(ingredient_string=raw_ingredient)
                    parsed = self.ingredient_service.parse_ingredient(parse_request)
                    ingredients.append(ParsedIngredient(
                        name=parsed.name,
                        amount=parsed.amount,
                        unit=parsed.unit,
                        is_well_formed=parsed.is_well_formed,
                        raw_text=raw_ingredient
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse ingredient '{raw_ingredient}': {str(e)}")
                    # Add as unparsed ingredient
                    ingredients.append(ParsedIngredient(
                        name=raw_ingredient,
                        is_well_formed=False,
                        raw_text=raw_ingredient
                    ))

            # Estimate effort based on total time
            effort = self._estimate_effort(total_time_minutes)

            logger.info(f"Successfully parsed recipe: title={title}, ingredients={len(ingredients)}, time={total_time_minutes}min, effort={effort}")

            return ParseRecipeResponse(
                title=title,
                description=description,
                total_time_minutes=total_time_minutes,
                effort=effort,
                ingredients=ingredients,
                url=request.url
            )

        except Exception as e:
            logger.error(f"Error parsing recipe from {request.url}: {str(e)}")
            # Return minimal response with error info
            return ParseRecipeResponse(
                title=None,
                description=f"Failed to parse recipe: {str(e)}",
                url=request.url
            )

    def _fetch_url(self, url: str) -> str:
        """Fetch HTML content from URL"""
        logger.info(f"Fetching URL: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        logger.info(f"Successfully fetched {len(response.content)} bytes")
        return response.text

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract recipe title, trying OpenGraph first then falling back to HTML"""

        # Try OpenGraph
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            logger.info(f"Found title in OpenGraph: {og_title['content']}")
            return og_title['content'].strip()

        # Try schema.org structured data
        title_elem = soup.find(attrs={'itemprop': 'name'})
        if title_elem:
            title = title_elem.get_text().strip()
            if title:
                logger.info(f"Found title in schema.org markup: {title}")
                return title

        # Try h1 heading
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text().strip()
            if title:
                logger.info(f"Found title in h1: {title}")
                return title

        # Fallback to <title> tag
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            logger.info(f"Found title in <title> tag: {title}")
            return title

        logger.warning("Could not find recipe title")
        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract recipe description, trying OpenGraph first then falling back to HTML"""

        # Try OpenGraph
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            logger.info(f"Found description in OpenGraph")
            return og_desc['content'].strip()

        # Try meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            logger.info(f"Found description in meta tag")
            return meta_desc['content'].strip()

        # Try schema.org structured data
        desc_elem = soup.find(attrs={'itemprop': 'description'})
        if desc_elem:
            desc = desc_elem.get_text().strip()
            if desc:
                logger.info(f"Found description in schema.org markup")
                return desc

        logger.warning("Could not find recipe description")
        return None

    def _extract_time(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract total cooking time in minutes"""

        # Try to extract prep time and cook time separately
        prep_time = self._extract_time_value(soup, 'prepTime')
        cook_time = self._extract_time_value(soup, 'cookTime')
        total_time = self._extract_time_value(soup, 'totalTime')

        # If we have total time, use it
        if total_time:
            logger.info(f"Found total time: {total_time} minutes")
            return total_time

        # Otherwise, sum prep and cook time
        if prep_time or cook_time:
            total = (prep_time or 0) + (cook_time or 0)
            logger.info(f"Calculated total time from prep ({prep_time}) + cook ({cook_time}) = {total} minutes")
            return total if total > 0 else None

        logger.warning("Could not find recipe time information")
        return None

    def _extract_time_value(self, soup: BeautifulSoup, time_type: str) -> Optional[int]:
        """Extract a specific time value (prepTime, cookTime, totalTime) in minutes"""

        # Try schema.org structured data (ISO 8601 duration format)
        time_elem = soup.find(attrs={'itemprop': time_type})
        if time_elem:
            # Check for datetime attribute (ISO 8601 format like "PT30M")
            datetime_val = time_elem.get('datetime')
            if datetime_val:
                minutes = self._parse_iso_duration(datetime_val)
                if minutes:
                    return minutes

            # Try parsing text content
            text = time_elem.get_text().strip()
            minutes = self._parse_time_text(text)
            if minutes:
                return minutes

        # Try searching for time in various text patterns
        # Look for patterns like "Prep: 30 minutes", "Cook time: 1 hour"
        time_patterns = [
            (rf'{time_type}:\s*(\d+)\s*(?:min|minute)', 1),
            (rf'{time_type}:\s*(\d+)\s*(?:hr|hour)', 60),
        ]

        for pattern, multiplier in time_patterns:
            match = soup.find(text=re.compile(pattern, re.IGNORECASE))
            if match:
                result = re.search(pattern, match, re.IGNORECASE)
                if result:
                    return int(result.group(1)) * multiplier

        return None

    def _parse_iso_duration(self, duration: str) -> Optional[int]:
        """Parse ISO 8601 duration format (e.g., PT30M, PT1H30M) to minutes"""
        try:
            # Remove 'PT' prefix
            if not duration.startswith('PT'):
                return None

            duration = duration[2:]

            hours = 0
            minutes = 0

            # Extract hours
            h_match = re.search(r'(\d+)H', duration)
            if h_match:
                hours = int(h_match.group(1))

            # Extract minutes
            m_match = re.search(r'(\d+)M', duration)
            if m_match:
                minutes = int(m_match.group(1))

            total_minutes = hours * 60 + minutes
            return total_minutes if total_minutes > 0 else None
        except Exception as e:
            logger.warning(f"Failed to parse ISO duration '{duration}': {str(e)}")
            return None

    def _parse_time_text(self, text: str) -> Optional[int]:
        """Parse time from text like '30 minutes', '1 hour 30 minutes', etc."""
        try:
            total_minutes = 0

            # Look for hours
            h_match = re.search(r'(\d+)\s*(?:hr|hour|hours)', text, re.IGNORECASE)
            if h_match:
                total_minutes += int(h_match.group(1)) * 60

            # Look for minutes
            m_match = re.search(r'(\d+)\s*(?:min|minute|minutes)', text, re.IGNORECASE)
            if m_match:
                total_minutes += int(m_match.group(1))

            return total_minutes if total_minutes > 0 else None
        except Exception as e:
            logger.warning(f"Failed to parse time text '{text}': {str(e)}")
            return None

    def _extract_ingredients(self, soup: BeautifulSoup) -> List[str]:
        """Extract ingredient list from HTML"""

        ingredients = []

        # Try schema.org structured data
        ingredient_elems = soup.find_all(attrs={'itemprop': 'recipeIngredient'})
        if ingredient_elems:
            for elem in ingredient_elems:
                text = elem.get_text().strip()
                if text:
                    ingredients.append(text)
            if ingredients:
                logger.info(f"Found {len(ingredients)} ingredients in schema.org markup")
                return ingredients

        # Try common CSS classes
        common_classes = [
            'ingredient',
            'recipe-ingredient',
            'ingredients-item',
            'ingredient-text',
            'ingredient-list',
            'structured-ingredients__list-item'
        ]

        for class_name in common_classes:
            elems = soup.find_all(class_=re.compile(class_name, re.IGNORECASE))
            if elems:
                for elem in elems:
                    text = elem.get_text().strip()
                    if text and not text.startswith('Ingredients'):  # Skip header text
                        ingredients.append(text)
                if ingredients:
                    logger.info(f"Found {len(ingredients)} ingredients using class '{class_name}'")
                    return ingredients

        # Try to find an ingredients list by looking for a section with "ingredients" heading
        # followed by a list
        ingredients_section = soup.find(text=re.compile(r'ingredients', re.IGNORECASE))
        if ingredients_section:
            # Look for nearby ul or ol elements
            parent = ingredients_section.find_parent()
            if parent:
                list_elem = parent.find_next_sibling(['ul', 'ol'])
                if not list_elem:
                    list_elem = parent.find(['ul', 'ol'])

                if list_elem:
                    for li in list_elem.find_all('li'):
                        text = li.get_text().strip()
                        if text:
                            ingredients.append(text)
                    if ingredients:
                        logger.info(f"Found {len(ingredients)} ingredients in list after 'Ingredients' heading")
                        return ingredients

        logger.warning("Could not find ingredients in HTML")
        return ingredients

    def _estimate_effort(self, total_time_minutes: Optional[int]) -> Optional[Effort]:
        """Estimate recipe effort based on total time"""

        if total_time_minutes is None:
            return None

        if total_time_minutes < 30:
            return Effort.LOW
        elif total_time_minutes < 60:
            return Effort.MEDIUM
        else:
            return Effort.HIGH
