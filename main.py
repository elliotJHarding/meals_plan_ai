from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
import logging
import time
import json

from meals_contract.models import *

from meal_plan_chat_service import MealPlanChatService
from recipe_service import RecipeService
from ingredient_service import IngredientService
from ingredient_suggestion_service import IngredientSuggestionService
from auth_utils import extract_bearer_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Meal Plan AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

meal_plan_chat_service = MealPlanChatService()
recipe_service = RecipeService()
ingredient_service = IngredientService()
ingredient_suggestion_service = IngredientSuggestionService()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log request details
    logger.info(f"🔵 Incoming {request.method} {request.url.path}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    # Get request body for POST requests
    if request.method == "POST":
        try:
            body = await request.body()
            if body:
                # Try to parse as JSON for pretty logging
                try:
                    json_body = json.loads(body)
                    logger.info(f"Request body (JSON): {json.dumps(json_body, indent=2, default=str)}")
                except json.JSONDecodeError:
                    logger.info(f"Request body (raw): {body.decode('utf-8')[:1000]}...")
            
            # Recreate request with body for downstream processing
            async def receive():
                return {"type": "http.request", "body": body}
            
            request._receive = receive
        except Exception as e:
            logger.warning(f"Could not read request body: {e}")
    
    # Process request
    response = await call_next(request)
    
    # Log response details
    process_time = time.time() - start_time
    logger.info(f"🟢 Response {response.status_code} for {request.method} {request.url.path}")
    logger.info(f"Processing time: {process_time:.3f}s")
    logger.info(f"Response headers: {dict(response.headers)}")
    
    return response


@app.get("/")
async def root():
    return {"message": "Meal Plan AI API", "status": "running"}


@app.post("/parse-recipe", response_model=ParseRecipeResponse)
async def parse_recipe(request: ParseRecipeRequest):
    """
    Parse a recipe from a URL.
    Extracts title, description, time, effort, and ingredients.
    """
    try:
        logger.info(f"=== RECIPE PARSING REQUEST ===")
        logger.info(f"URL: {request.url}")

        response = recipe_service.parse_recipe(request)

        logger.info(f"=== RECIPE PARSING RESPONSE ===")
        logger.info(f"Title: {response.title}")
        logger.info(f"Ingredients found: {len(response.ingredients)}")
        logger.info(f"Total time: {response.total_time_minutes} minutes")
        logger.info(f"Effort: {response.effort}")
        logger.info("=== REQUEST COMPLETED SUCCESSFULLY ===")

        return response
    except Exception as e:
        logger.error(f"=== RECIPE PARSING ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        logger.error("=== ERROR HANDLING COMPLETED ===")
        raise HTTPException(status_code=500, detail=f"Failed to parse recipe: {str(e)}")


@app.post("/parse-ingredient", response_model=ParseIngredientResponse)
async def parse_ingredient(request: ParseIngredientRequest):
    """
    Parse an ingredient string into structured components.
    Handles complex quantities like fractions and ranges.
    """
    try:
        logger.info(f"=== INGREDIENT PARSING REQUEST ===")
        logger.info(f"Ingredient string: {request.ingredient_string}")

        response = ingredient_service.parse_ingredient(request)

        logger.info(f"=== INGREDIENT PARSING RESPONSE ===")
        logger.info(f"Name: {response.name}")
        logger.info(f"Amount: {response.amount}")
        logger.info(f"Unit: {response.unit}")
        logger.info(f"Well-formed: {response.is_well_formed}")
        logger.info("=== REQUEST COMPLETED SUCCESSFULLY ===")

        return response
    except Exception as e:
        logger.error(f"=== INGREDIENT PARSING ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        logger.error("=== ERROR HANDLING COMPLETED ===")
        raise HTTPException(status_code=500, detail=f"Failed to parse ingredient: {str(e)}")


@app.post("/ingredient-metadata", response_model=IngredientMetadataResponse)
async def get_ingredient_metadata(request_body: IngredientMetadataRequest, request: Request):
    """
    Get metadata for an ingredient.
    Uses AI to classify ingredients as CUPBOARD or FRESH.
    Requires OAuth authentication via Authorization header.
    """
    try:
        logger.info(f"=== INGREDIENT METADATA REQUEST ===")
        logger.info(f"Ingredient: {request_body.ingredient_name}")

        # Extract OAuth token from Authorization header
        access_token = extract_bearer_token(request)

        # Call service with OAuth token
        response = ingredient_service.get_ingredient_metadata(request_body, access_token)

        logger.info(f"=== INGREDIENT METADATA RESPONSE ===")
        logger.info(f"Storage type: {response.storage_type}")
        logger.info(f"Description: {response.description}")
        logger.info("=== REQUEST COMPLETED SUCCESSFULLY ===")

        return response
    except HTTPException:
        # Re-raise auth errors (401)
        raise
    except Exception as e:
        logger.error(f"=== INGREDIENT METADATA ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        logger.error("=== ERROR HANDLING COMPLETED ===")
        raise HTTPException(status_code=500, detail=f"Failed to get ingredient metadata: {str(e)}")


@app.post("/chat-meal-plan-day", response_model=DayMealPlanChatResponse)
async def chat_meal_plan_day(request_body: DayMealPlanChatRequest, request: Request):
    """
    Chat-based meal planning for a specific day.
    Supports iterative conversation - suggest meals, get feedback, adjust suggestions.
    Requires OAuth authentication via Authorization header.
    """
    try:
        logger.info(f"=== MEAL PLAN CHAT REQUEST ===")
        logger.info(f"Day: {request_body.day_of_week}")
        logger.info(f"Calendar events: {len(request_body.calendar_events)}")
        logger.info(f"Available meals: {len(request_body.available_meals)}")
        logger.info(f"Conversation history: {len(request_body.conversation_history)} messages")

        # Log conversation history
        if request_body.conversation_history:
            logger.info("Previous conversation:")
            for i, msg in enumerate(request_body.conversation_history):
                logger.info(f"  {i+1}. {msg.role}: {msg.content[:100]}...")

        # Extract OAuth token from Authorization header
        access_token = extract_bearer_token(request)

        # Call service with OAuth token
        response = meal_plan_chat_service.suggest_meals_for_day(request_body, access_token)

        logger.info(f"=== MEAL PLAN CHAT RESPONSE ===")
        logger.info(f"Suggestions: {len(response.suggestions)}")
        for suggestion in response.suggestions:
            logger.info(f"  Rank {suggestion.rank}: {suggestion.meal_name}")
        logger.info(f"Reasoning: {response.reasoning[:200]}...")
        logger.info("=== REQUEST COMPLETED SUCCESSFULLY ===")

        return response
    except HTTPException:
        # Re-raise auth errors (401)
        raise
    except Exception as e:
        logger.error(f"=== MEAL PLAN CHAT ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        logger.error("=== ERROR HANDLING COMPLETED ===")
        raise HTTPException(status_code=500, detail=f"Failed to generate meal suggestions: {str(e)}")


@app.post("/suggest-ingredients", response_model=SuggestIngredientsResponse)
async def suggest_ingredients(request_body: SuggestIngredientsRequest, request: Request):
    """
    Suggest ingredients for a meal using AI.
    Requires OAuth authentication via Authorization header.
    """
    try:
        logger.info(f"=== INGREDIENT SUGGESTION REQUEST ===")
        logger.info(f"Meal: {request_body.meal_name}")

        access_token = extract_bearer_token(request)
        response = ingredient_suggestion_service.suggest_ingredients(request_body, access_token)

        logger.info(f"=== INGREDIENT SUGGESTION RESPONSE ===")
        logger.info(f"Suggested {len(response.ingredients)} ingredients")
        logger.info("=== REQUEST COMPLETED SUCCESSFULLY ===")

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== INGREDIENT SUGGESTION ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        logger.error("=== ERROR HANDLING COMPLETED ===")
        raise HTTPException(status_code=500, detail=f"Failed to suggest ingredients: {str(e)}")
