from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Set, Union, Any
from datetime import datetime, date
from enum import Enum


class Effort(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MealTag(str, Enum):
    VEGETARIAN = "VEGETARIAN"
    VEGAN = "VEGAN"
    GLUTEN_FREE = "GLUTEN_FREE"
    DAIRY_FREE = "DAIRY_FREE"
    QUICK = "QUICK"
    HEALTHY = "HEALTHY"
    COMFORT_FOOD = "COMFORT_FOOD"
    SPICY = "SPICY"
    BUDGET_FRIENDLY = "BUDGET_FRIENDLY"
    FAMILY_FRIENDLY = "FAMILY_FRIENDLY"


class UserDto(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None


class ImageDto(BaseModel):
    id: Optional[int] = None
    url: Optional[str] = None
    alt_text: Optional[str] = None


class IngredientDto(BaseModel):
    model_config = {"populate_by_name": True}
    
    id: Optional[int] = None
    name: str
    quantity: Optional[Union[str, float, int]] = Field(None, alias="amount")
    unit: Optional[Union[str, dict]] = None
    index: Optional[int] = None
    metadata: Optional[dict] = None
    
    @field_validator('quantity', mode='before')
    @classmethod
    def parse_quantity(cls, v):
        if isinstance(v, (int, float)):
            return str(v)
        return v
    
    @field_validator('unit', mode='before')
    @classmethod
    def parse_unit(cls, v):
        if isinstance(v, dict) and 'code' in v:
            return v['code']
        return v


class RecipeDto(BaseModel):
    model_config = {"populate_by_name": True}
    
    id: Optional[int] = None
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None
    image: Optional[ImageDto] = None


class MealDto(BaseModel):
    model_config = {"populate_by_name": True}
    
    id: Optional[int] = None
    name: str
    effort: Optional[Effort] = None
    image: Optional[ImageDto] = None
    description: Optional[str] = None
    serves: Optional[int] = None
    prep_time_minutes: Optional[int] = Field(None, alias="prepTimeMinutes")
    ingredients: Optional[List[IngredientDto]] = None
    recipe: Optional[RecipeDto] = None
    tags: Optional[List[Union[MealTag, dict]]] = None
    
    @field_validator('tags', mode='before')
    @classmethod
    def parse_tags(cls, v):
        if v is None:
            return v
        
        parsed_tags = []
        for tag in v:
            if isinstance(tag, dict) and 'name' in tag:
                # Map the tag name to our enum
                tag_name = tag['name'].upper().replace(' ', '_')
                # Try to find matching enum value
                for meal_tag in MealTag:
                    if meal_tag.value == tag_name or meal_tag.name == tag_name:
                        parsed_tags.append(meal_tag)
                        break
            elif isinstance(tag, str):
                parsed_tags.append(tag)
            else:
                parsed_tags.append(tag)
        
        return parsed_tags


class ShoppingListItemDto(BaseModel):
    id: Optional[int] = None
    ingredient_name: str
    quantity: Optional[str] = None
    unit: Optional[str] = None
    checked: Optional[bool] = False


class PlanMealDto(BaseModel):
    model_config = {"populate_by_name": True}
    
    id: Optional[int] = None
    meal: MealDto
    required_servings: int = Field(alias="requiredServings")


class PlanDto(BaseModel):
    model_config = {"populate_by_name": True}
    
    id: Optional[int] = None
    date: date
    plan_meals: List[PlanMealDto] = Field(alias="planMeals")
    shopping_list_items: Optional[List[ShoppingListItemDto]] = Field(None, alias="shoppingListItems")


class CalendarEventDto(BaseModel):
    model_config = {"populate_by_name": True}
    
    name: str
    time: Union[datetime, List[int]]
    colour: Optional[str] = None
    text_colour: Optional[str] = Field(None, alias="textColour")
    all_day: bool = Field(False, alias="allDay")
    
    @field_validator('time', mode='before')
    @classmethod
    def parse_time(cls, v):
        if isinstance(v, list) and len(v) >= 5:
            # Convert [year, month, day, hour, minute] to datetime
            return datetime(v[0], v[1], v[2], v[3], v[4])
        return v


class AiMealPlanGenerationRequest(BaseModel):
    model_config = {"populate_by_name": True}
    
    week_start_date: Union[date, int] = Field(alias="weekStartDate")
    week_end_date: Union[date, int] = Field(alias="weekEndDate")
    available_meals: List[MealDto] = Field(alias="availableMeals")
    recent_meal_plans: List[PlanDto] = Field(alias="recentMealPlans")
    existing_plans_for_week: List[PlanDto] = Field(alias="existingPlansForWeek")
    calendar_events: List[CalendarEventDto] = Field(alias="calendarEvents")
    prompt: Optional[str] = None
    
    @field_validator('week_start_date', 'week_end_date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, int):
            # Convert Unix timestamp (milliseconds) to date
            return date.fromtimestamp(v / 1000)
        return v


class AiMealPlanGenerationResponse(BaseModel):
    model_config = {"populate_by_name": True}
    
    generated_plans: List[PlanDto] = Field(alias="generatedPlans")
    reasoning: str