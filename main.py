from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
import json

from models import AiMealPlanGenerationRequest, AiMealPlanGenerationResponse
from meal_plan_service import MealPlanService

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

meal_plan_service = MealPlanService()


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


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.post("/generate-meal-plan", response_model=AiMealPlanGenerationResponse)
async def generate_meal_plan(request: AiMealPlanGenerationRequest):
    try:
        # Log detailed request information
        logger.info("=== MEAL PLAN GENERATION REQUEST ===")
        logger.info(f"Week period: {request.week_start_date} to {request.week_end_date}")
        logger.info(f"Available meals count: {len(request.available_meals)}")
        logger.info(f"Recent meal plans count: {len(request.recent_meal_plans)}")
        logger.info(f"Existing plans for week count: {len(request.existing_plans_for_week)}")
        logger.info(f"Calendar events count: {len(request.calendar_events)}")
        logger.info(f"Custom prompt: {request.prompt if request.prompt else 'None'}")
        
        # Log available meals details
        if request.available_meals:
            logger.info("Available meals:")
            for i, meal in enumerate(request.available_meals):
                effort = meal.effort.value if meal.effort else 'Unknown'
                tags = [tag.value if hasattr(tag, 'value') else str(tag) for tag in meal.tags] if meal.tags else []
                logger.info(f"  {i+1}. {meal.name} (Effort: {effort}, Serves: {meal.serves}, Prep: {meal.prep_time_minutes}min, Tags: {tags})")
        
        # Log calendar events
        if request.calendar_events:
            logger.info("Calendar events:")
            for i, event in enumerate(request.calendar_events):
                logger.info(f"  {i+1}. {event.name} at {event.time} ({'All day' if event.all_day else 'Timed'})")
        
        # Log recent meal plans
        if request.recent_meal_plans:
            logger.info("Recent meal plans:")
            for i, plan in enumerate(request.recent_meal_plans):
                meal_names = [pm.meal.name for pm in plan.plan_meals]
                logger.info(f"  {i+1}. {plan.date}: {', '.join(meal_names)}")
        
        # Log existing plans for the week
        if request.existing_plans_for_week:
            logger.info("Existing plans for week:")
            for i, plan in enumerate(request.existing_plans_for_week):
                meal_names = [pm.meal.name for pm in plan.plan_meals]
                logger.info(f"  {i+1}. {plan.date}: {', '.join(meal_names)}")
        
        # Generate meal plan
        logger.info("Calling meal plan service...")
        response = meal_plan_service.generate_meal_plan(request)
        
        # Log response details
        logger.info("=== MEAL PLAN GENERATION RESPONSE ===")
        logger.info(f"Generated plans count: {len(response.generated_plans)}")
        logger.info("Generated meal plan:")
        for i, plan in enumerate(response.generated_plans):
            meal_names = [pm.meal.name for pm in plan.plan_meals]
            servings = [pm.required_servings for pm in plan.plan_meals]
            logger.info(f"  {plan.date}: {', '.join([f'{name} ({srv} servings)' for name, srv in zip(meal_names, servings)])}")
        
        logger.info(f"Reasoning: {response.reasoning}")
        logger.info("=== REQUEST COMPLETED SUCCESSFULLY ===")
        
        return response
        
    except Exception as e:
        logger.error("=== MEAL PLAN GENERATION ERROR ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error("Request details for debugging:")
        logger.error(f"  Week: {getattr(request, 'week_start_date', 'N/A')} to {getattr(request, 'week_end_date', 'N/A')}")
        logger.error(f"  Meals count: {len(getattr(request, 'available_meals', []))}")
        
        # Log the full stack trace for debugging
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        logger.error("=== ERROR HANDLING COMPLETED ===")
        
        raise HTTPException(status_code=500, detail=f"Failed to generate meal plan: {str(e)}")
