import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from meals_contract.models.suggest_ingredients_request import SuggestIngredientsRequest
from meals_contract.models.suggest_ingredients_response import SuggestIngredientsResponse
from meals_contract.models.suggested_ingredient import SuggestedIngredient

from auth_utils import create_llm_with_token

logger = logging.getLogger(__name__)


class IngredientSuggestionItem(BaseModel):
    name: str = Field(description="Ingredient name")
    amount: Optional[float] = Field(default=None, description="Quantity")
    unit_code: Optional[str] = Field(default=None, description="Unit code (e.g., 'tsp', 'g', 'cup') or null for countable items")


class IngredientSuggestionOutput(BaseModel):
    ingredients: List[IngredientSuggestionItem] = Field(description="List of suggested ingredients")
    reasoning: str = Field(description="Brief explanation of the suggestions")


class IngredientSuggestionService:

    def __init__(self):
        self.output_parser = PydanticOutputParser(pydantic_object=IngredientSuggestionOutput)

    def _get_llm(self, access_token: str):
        return create_llm_with_token(
            access_token=access_token,
            model="gemini-flash-latest",
            temperature=0.4
        )

    def suggest_ingredients(self, request: SuggestIngredientsRequest, access_token: str) -> SuggestIngredientsResponse:
        logger.info(f"Suggesting ingredients for meal: {request.meal_name}")

        existing_text = ""
        if request.existing_ingredients and len(request.existing_ingredients) > 0:
            existing_items = []
            for ing in request.existing_ingredients:
                parts = []
                if ing.amount:
                    parts.append(str(ing.amount))
                if ing.unit_code:
                    parts.append(ing.unit_code)
                parts.append(ing.name)
                existing_items.append(" ".join(parts))
            existing_text = f"\n\nExisting ingredients (do NOT suggest these again):\n- " + "\n- ".join(existing_items)

        tags_text = ""
        if request.tags and len(request.tags) > 0:
            tags_text = f"\nTags: {', '.join(request.tags)}"

        serves_text = ""
        if request.serves:
            serves_text = f"\nServes: {request.serves} people"

        description_text = ""
        if request.meal_description:
            description_text = f"\nDescription: {request.meal_description}"

        recipe_text = ""
        if request.recipe_url:
            recipe_text = f"\nRecipe URL: {request.recipe_url}"

        prompt_template = ChatPromptTemplate.from_template("""You are a culinary expert. Suggest ingredients for a meal.

Meal name: {meal_name}{description}{tags}{serves}{recipe_url}{existing}

Rules:
- Suggest a complete, practical list of ingredients for this meal
- If existing ingredients are listed, only suggest the MISSING ones
- Scale quantities for the serving count if provided
- Use these unit codes where appropriate: tsp, tbsp, cup, ml, l, g, kg, oz, lb, pinch, clove, slice, piece, can, bunch
- Use null for unit_code when items are countable (e.g., 2 eggs, 1 onion)
- Respect dietary tags (e.g., vegetarian = no meat/fish)
- Order logically: proteins first, then vegetables, then pantry/spice items
- Be practical and realistic with quantities

{format_instructions}""")

        prompt = prompt_template.format(
            meal_name=request.meal_name,
            description=description_text,
            tags=tags_text,
            serves=serves_text,
            recipe_url=recipe_text,
            existing=existing_text,
            format_instructions=self.output_parser.get_format_instructions()
        )

        try:
            llm = self._get_llm(access_token)
            response = llm.invoke(prompt)
            logger.info(f"Received AI response (length: {len(response.content)} chars)")

            parsed = self.output_parser.parse(response.content)

            suggested = [
                SuggestedIngredient(
                    name=item.name,
                    amount=item.amount,
                    unit_code=item.unit_code
                )
                for item in parsed.ingredients
            ]

            logger.info(f"Suggested {len(suggested)} ingredients for '{request.meal_name}'")
            return SuggestIngredientsResponse(
                ingredients=suggested,
                reasoning=parsed.reasoning
            )
        except Exception as e:
            logger.error(f"Error suggesting ingredients: {str(e)}")
            raise
