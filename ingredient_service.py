import os
import re
import logging
from fractions import Fraction
from typing import Optional, Tuple
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from meals_contract.models.parse_ingredient_request import ParseIngredientRequest
from meals_contract.models.parse_ingredient_response import ParseIngredientResponse
from meals_contract.models.ingredient_metadata_request import IngredientMetadataRequest
from meals_contract.models.ingredient_metadata_response import IngredientMetadataResponse
from meals_contract.models.ingredient_storage_type import IngredientStorageType

from auth_utils import create_llm_with_token

load_dotenv()

logger = logging.getLogger(__name__)


class IngredientService:
    # Unicode fraction mappings
    UNICODE_FRACTIONS = {
        '¼': '1/4',
        '½': '1/2',
        '¾': '3/4',
        '⅐': '1/7',
        '⅑': '1/9',
        '⅒': '1/10',
        '⅓': '1/3',
        '⅔': '2/3',
        '⅕': '1/5',
        '⅖': '2/5',
        '⅗': '3/5',
        '⅘': '4/5',
        '⅙': '1/6',
        '⅚': '5/6',
        '⅛': '1/8',
        '⅜': '3/8',
        '⅝': '5/8',
        '⅞': '7/8',
    }

    # Common cooking units
    UNITS = {
        # Volume
        'cup', 'cups', 'c',
        'tablespoon', 'tablespoons', 'tbsp', 'tbs', 'tb',
        'teaspoon', 'teaspoons', 'tsp', 'ts',
        'fluid ounce', 'fluid ounces', 'fl oz', 'floz',
        'pint', 'pints', 'pt',
        'quart', 'quarts', 'qt',
        'gallon', 'gallons', 'gal',
        'milliliter', 'milliliters', 'ml',
        'liter', 'liters', 'l',

        # Weight
        'pound', 'pounds', 'lb', 'lbs',
        'ounce', 'ounces', 'oz',
        'gram', 'grams', 'g',
        'kilogram', 'kilograms', 'kg',

        # Other
        'pinch', 'pinches',
        'dash', 'dashes',
        'clove', 'cloves',
        'slice', 'slices',
        'piece', 'pieces',
        'can', 'cans',
        'package', 'packages', 'pkg',
        'bunch', 'bunches',
        'head', 'heads',
        'sprig', 'sprigs',
        'stalk', 'stalks',
        'stick', 'sticks',
        'whole',
        'small', 'medium', 'large',
    }

    def __init__(self):
        self.metadata_parser = PydanticOutputParser(pydantic_object=IngredientMetadataResponse)

    def _get_llm(self, access_token: str) -> ChatGoogleGenerativeAI:
        """Create LLM instance with user's OAuth token"""
        return create_llm_with_token(
            access_token=access_token,
            model="gemini-flash-latest",
            temperature=0.3  # Lower temperature for more consistent metadata
        )

    def parse_ingredient(self, request: ParseIngredientRequest) -> ParseIngredientResponse:
        """
        Parse an ingredient string into structured components.
        Handles complex quantities like fractions, ranges, and decimals.

        Examples:
        - "2 1/2 cups all-purpose flour" -> amount: "2.5", unit: "cups", name: "all-purpose flour"
        - "1-2 medium onions, diced" -> amount: "1-2", unit: "medium", name: "onions, diced"
        - "a pinch of salt" -> amount: "1", unit: "pinch", name: "salt"
        """
        logger.info(f"Parsing ingredient: {request.ingredient_string}")

        ingredient_str = request.ingredient_string.strip()

        # Check for obviously malformed input
        if not ingredient_str or len(ingredient_str) < 2:
            logger.warning(f"Ingredient string too short: {ingredient_str}")
            return ParseIngredientResponse(
                name=ingredient_str,
                is_well_formed=False,
                raw_text=ingredient_str
            )

        # Try to parse the ingredient
        try:
            amount, unit, name = self._parse_ingredient_parts(ingredient_str)

            # Determine if it's well-formed
            is_well_formed = bool(name and (amount or unit))

            logger.info(f"Parsed: amount={amount}, unit={unit}, name={name}, well_formed={is_well_formed}")

            return ParseIngredientResponse(
                name=name or ingredient_str,
                amount=amount,
                unit=unit,
                is_well_formed=is_well_formed,
                raw_text=ingredient_str
            )
        except Exception as e:
            logger.error(f"Error parsing ingredient '{ingredient_str}': {str(e)}")
            return ParseIngredientResponse(
                name=ingredient_str,
                is_well_formed=False,
                raw_text=ingredient_str
            )

    def _normalize_fractions(self, text: str) -> str:
        """Convert Unicode fractions to ASCII format (e.g., ¾ -> 3/4)"""
        for unicode_frac, ascii_frac in self.UNICODE_FRACTIONS.items():
            text = text.replace(unicode_frac, ascii_frac)
        return text

    def _parse_ingredient_parts(self, ingredient_str: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse ingredient string into amount, unit, and name components"""

        # Normalize the string and convert Unicode fractions
        text = self._normalize_fractions(ingredient_str.strip())

        # Pattern to match quantities (including fractions and ranges)
        # Matches: "2", "1/2", "2 1/2", "1-2", "0.5", "3/4", etc.
        # Handles fractions at the start after Unicode normalization
        quantity_pattern = r'^(?:(\d+(?:\.\d+)?)\s+)?(\d+/\d+|\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)'

        # Handle special cases like "a pinch", "a dash"
        if re.match(r'^a\s+(pinch|dash)', text, re.IGNORECASE):
            match = re.match(r'^a\s+(pinch|dash)\s+of\s+(.+)', text, re.IGNORECASE)
            if match:
                return "1", match.group(1).lower(), match.group(2).strip()
            return "1", "pinch", text[2:].strip()

        amount = None
        unit = None
        name = text

        # Try to extract quantity
        match = re.match(quantity_pattern, text.strip())
        if match:
            whole_part = match.group(1)
            frac_or_num = match.group(2)

            # Calculate the total amount
            total = 0
            if whole_part:
                total += float(whole_part)

            # Handle fraction (e.g., "1/2")
            if '/' in frac_or_num:
                frac = Fraction(frac_or_num)
                total += float(frac)
                amount = str(total) if total != int(total) else str(int(total))
            # Handle range (e.g., "1-2")
            elif '-' in frac_or_num:
                amount = frac_or_num.strip()
            # Handle decimal or integer
            else:
                total += float(frac_or_num)
                amount = str(total) if total != int(total) else str(int(total))

            # Remove the quantity from the text
            text = text[match.end():].strip()

        # Try to extract unit
        if text:
            # Check if the beginning of the remaining text is a known unit
            words = text.split()
            if words:
                first_word = words[0].lower().rstrip('.,;')
                # Check for compound units like "fluid ounce" or size descriptors
                if len(words) > 1:
                    two_words = f"{words[0].lower()} {words[1].lower()}".rstrip('.,;')
                    if two_words in self.UNITS:
                        unit = two_words
                        text = ' '.join(words[2:]).strip()
                    elif first_word in self.UNITS:
                        unit = first_word
                        text = ' '.join(words[1:]).strip()
                    else:
                        # Check if it's a size descriptor (small, medium, large)
                        if first_word in {'small', 'medium', 'large'}:
                            unit = first_word
                            text = ' '.join(words[1:]).strip()
                elif first_word in self.UNITS:
                    unit = first_word
                    text = ' '.join(words[1:]).strip()

        # Clean up the remaining text (ingredient name)
        # Remove leading "of" if present
        text = re.sub(r'^of\s+', '', text, flags=re.IGNORECASE)
        name = text.strip() if text else None

        return amount, unit, name

    def get_ingredient_metadata(
        self,
        request: IngredientMetadataRequest,
        access_token: str
    ) -> IngredientMetadataResponse:
        """
        Get metadata for an ingredient using AI classification.
        Determines if ingredient is typically stored in CUPBOARD or kept FRESH.

        Args:
            request: The ingredient metadata request
            access_token: User's OAuth access token for Google Gemini API

        Returns:
            IngredientMetadataResponse with classification
        """
        logger.info(f"Getting metadata for ingredient: {request.ingredient_name}")

        prompt_template = ChatPromptTemplate.from_template("""
You are a culinary expert helping to classify ingredients by their typical storage requirements.

Classify the following ingredient as either CUPBOARD, FRESH or FREEZER:

Ingredient: {ingredient_name}

Classification criteria:
- CUPBOARD: Dry goods, spices, canned items, oils, condiments, grains, pasta, flour, sugar, etc.
  Items with long shelf life that don't require refrigeration.
- FRESH: Produce, dairy, meat, fish, eggs, fresh herbs, items that require refrigeration or have short shelf life.
- FREEZER: Any ingredient that requires freezing to maintain longevity.

Provide a brief description explaining the classification.

{format_instructions}
""")

        prompt = prompt_template.format(
            ingredient_name=request.ingredient_name,
            format_instructions=self.metadata_parser.get_format_instructions()
        )

        try:
            logger.info("Creating LLM with user's OAuth token...")
            llm = self._get_llm(access_token)

            logger.info("Calling Google Generative AI for ingredient metadata...")
            response = llm.invoke(prompt)
            logger.info(f"Received AI response (length: {len(response.content)} chars)")
            logger.debug(f"Raw AI response:\n{response.content}")

            # Parse the response
            parsed_response = self.metadata_parser.parse(response.content)
            logger.info(f"Successfully classified '{request.ingredient_name}' as {parsed_response.storage_type}")

            return parsed_response
        except Exception as e:
            logger.error(f"Error getting ingredient metadata: {str(e)}")
            # Fallback: use simple heuristics
            return self._get_fallback_metadata(request.ingredient_name)

    def _get_fallback_metadata(self, ingredient_name: str) -> IngredientMetadataResponse:
        """Fallback metadata classification using simple heuristics"""
        logger.info(f"Using fallback classification for: {ingredient_name}")

        ingredient_lower = ingredient_name.lower()

        # Simple keyword-based classification
        fresh_keywords = [
            'milk', 'cream', 'butter', 'cheese', 'yogurt',  # dairy
            'egg', 'eggs',  # eggs
            'chicken', 'beef', 'pork', 'fish', 'salmon', 'meat',  # proteins
            'lettuce', 'tomato', 'onion', 'garlic', 'carrot', 'potato',  # vegetables
            'apple', 'banana', 'orange', 'lemon', 'lime',  # fruits
            'basil', 'parsley', 'cilantro', 'dill', 'mint',  # fresh herbs
            'fresh', 'raw'
        ]

        for keyword in fresh_keywords:
            if keyword in ingredient_lower:
                return IngredientMetadataResponse(
                    ingredient_name=ingredient_name,
                    storage_type=IngredientStorageType.FRESH,
                    description="Typically requires refrigeration or has a short shelf life (fallback classification)"
                )

        # Default to CUPBOARD for everything else
        return IngredientMetadataResponse(
            ingredient_name=ingredient_name,
            storage_type=IngredientStorageType.CUPBOARD,
            description="Typically a dry good or shelf-stable item (fallback classification)"
        )
