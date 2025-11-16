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


# Recipe and Ingredient Parsing Models

class IngredientStorageType(str, Enum):
    CUPBOARD = "CUPBOARD"
    FRESH = "FRESH"


class ParseRecipeRequest(BaseModel):
    url: str = Field(..., description="URL of the recipe webpage to parse")


class ParsedIngredient(BaseModel):
    """Structured ingredient with parsed components"""
    name: str
    amount: Optional[str] = None
    unit: Optional[str] = None
    is_well_formed: bool = True
    raw_text: Optional[str] = None


class ParseRecipeResponse(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    total_time_minutes: Optional[int] = None
    effort: Optional[Effort] = None
    ingredients: List[ParsedIngredient] = []
    url: str


class ParseIngredientRequest(BaseModel):
    ingredient_string: str = Field(..., description="Raw ingredient string to parse (e.g., '2 1/2 cups all-purpose flour')")


class ParseIngredientResponse(BaseModel):
    name: str
    amount: Optional[str] = None
    unit: Optional[str] = None
    is_well_formed: bool
    raw_text: str


class IngredientMetadataRequest(BaseModel):
    ingredient_name: str = Field(..., description="Name of the ingredient to get metadata for")


class IngredientMetadataResponse(BaseModel):
    ingredient_name: str
    storage_type: IngredientStorageType
    description: Optional[str] = None


# Meal Plan Chat Models (Day-by-Day Planning)

class ChatMessage(BaseModel):
    """Represents a single message in the conversation"""
    role: str = Field(..., description="Role of the message sender: 'user' or 'assistant'")
    content: str = Field(..., description="The message content")


class SuggestedMeal(BaseModel):
    """Represents a meal suggestion with ranking information"""
    model_config = {"populate_by_name": True}

    meal_name: str = Field(alias="mealName")
    meal_id: int = Field(alias="mealId")
    rank: int = Field(..., description="Position in suggestions (1-5)", ge=1, le=5)
    suitability_score: Optional[float] = Field(None, alias="suitabilityScore", description="Confidence score 0-1", ge=0, le=1)


class DayMealPlanChatRequest(BaseModel):
    """Request for chatbot to suggest meals for a specific day"""
    model_config = {"populate_by_name": True}

    day_of_week: Union[date, int] = Field(alias="dayOfWeek", description="The specific day being planned")
    calendar_events: List[CalendarEventDto] = Field(alias="calendarEvents", description="Calendar events for this day")
    current_week_plan: Optional[List[PlanDto]] = Field(None, alias="currentWeekPlan", description="The full week's meal plan")
    recent_meal_plans: List[PlanDto] = Field(default_factory=list, alias="recentMealPlans", description="1-2 months of historical plans")
    available_meals: List[MealDto] = Field(alias="availableMeals", description="List of meals to choose from")
    conversation_history: List[ChatMessage] = Field(default_factory=list, alias="conversationHistory", description="Previous messages in conversation")
    chat_context: Optional[dict] = Field(None, alias="chatContext", description="Persistent context about user preferences and important information for meal planning")

    @field_validator('day_of_week', mode='before')
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, int):
            # Convert Unix timestamp (milliseconds) to date
            return date.fromtimestamp(v / 1000)
        return v


class DayMealPlanChatResponse(BaseModel):
    """Response from chatbot with meal suggestions"""
    model_config = {"populate_by_name": True}

    suggestions: List[SuggestedMeal]
    reasoning: str = Field(..., description="Explanation for the suggestions")
    conversation_complete: bool = Field(default=False, alias="conversationComplete", description="Whether more feedback is needed")
    updated_chat_context: Optional[dict] = Field(None, alias="updatedChatContext", description="Modified context if the LLM identified important information to remember for future meal planning")