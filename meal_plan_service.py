import os
import logging
from datetime import date, datetime
from typing import List
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from models import (
    AiMealPlanGenerationRequest,
    AiMealPlanGenerationResponse,
    PlanDto,
    PlanMealDto,
    MealDto,
    CalendarEventDto
)

load_dotenv()

logger = logging.getLogger(__name__)


class MealPlanService:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.7
        )
        self.output_parser = PydanticOutputParser(pydantic_object=AiMealPlanGenerationResponse)
        
    def generate_meal_plan(self, request: AiMealPlanGenerationRequest) -> AiMealPlanGenerationResponse:
        logger.info("--- Starting meal plan generation ---")
        
        prompt_template = ChatPromptTemplate.from_template("""
You are a helpful meal planning assistant. Your task is to generate a weekly meal plan based on the provided information.

CONTEXT:
- Week period: {week_start_date} to {week_end_date}
- Available meals: {available_meals}
- Recent meal plans: {recent_meal_plans}
- Calendar events: {calendar_events}

REQUIREMENTS:
1. Plan one main meal per day for the week
2. Consider meal effort levels in relation to calendar events (use low effort meals on busy days)
3. Avoid repeating meals from recent plans unless absolutely necessary
4. Ensure variety in meal types and effort levels throughout the week
5. Consider calendar events when planning - suggest easier meals on days with many events
6. Include a brief reasoning for your choices

IMPORTANT: 
- You must respond with valid JSON that matches the expected schema
- Include a 'generated_plans' array with one plan per day, and a 'reasoning' field explaining your choices
- For meals in the response, ONLY include the 'name' field - do not include any other meal properties like effort, ingredients, etc.

{format_instructions}
""")
        
        # Format available meals for prompt
        meal_summaries = []
        for meal in request.available_meals:
            effort_str = meal.effort.value if meal.effort else 'Unknown'
            meal_summary = f"- {meal.name} (Effort: {effort_str}, Serves: {meal.serves or 'N/A'}, Prep: {meal.prep_time_minutes or 'N/A'}min)"
            if meal.tags:
                tag_values = []
                for tag in meal.tags:
                    if hasattr(tag, 'value'):
                        tag_values.append(tag.value)
                    else:
                        tag_values.append(str(tag))
                meal_summary += f" [Tags: {', '.join(tag_values)}]"
            meal_summaries.append(meal_summary)
        
        logger.info(f"Formatted {len(meal_summaries)} meal summaries for prompt")
        
        # Format recent meals for context
        recent_meal_names = []
        for plan in request.recent_meal_plans:
            for plan_meal in plan.plan_meals:
                recent_meal_names.append(f"- {plan_meal.meal.name} on {plan.date}")
        
        logger.info(f"Formatted {len(recent_meal_names)} recent meals for context")
        
        # Format calendar events
        event_summaries = []
        for event in request.calendar_events:
            event_summaries.append(f"- {event.name} at {event.time} ({'All day' if event.all_day else 'Timed event'})")
        
        logger.info(f"Formatted {len(event_summaries)} calendar events for context")
        
        # Create the prompt
        prompt = prompt_template.format(
            week_start_date=request.week_start_date,
            week_end_date=request.week_end_date,
            available_meals="\n".join(meal_summaries) if meal_summaries else "No meals provided",
            recent_meal_plans="\n".join(recent_meal_names) if recent_meal_names else "No recent plans",
            calendar_events="\n".join(event_summaries) if event_summaries else "No calendar events",
            format_instructions=self.output_parser.get_format_instructions()
        )
        
        logger.info("Generated prompt for AI model")
        logger.debug(f"Full prompt:\n{prompt}")
        
        # Generate the response
        logger.info("Calling Google Generative AI...")
        try:
            response = self.llm.invoke(prompt)
            logger.info(f"Received AI response (length: {len(response.content)} chars)")
            logger.debug(f"Raw AI response:\n{response.content}")
        except Exception as e:
            logger.error(f"Error calling AI model: {str(e)}")
            return self._create_fallback_response(request, f"AI model error: {str(e)}")
        
        # Parse the response using the output parser
        try:
            logger.info("Parsing AI response...")
            parsed_response = self.output_parser.parse(response.content)
            
            # Simplify meals in the response to only include names
            simplified_response = self._simplify_response_meals(parsed_response)
            
            logger.info(f"Successfully parsed response with {len(simplified_response.generated_plans)} plans")
            logger.info("--- Meal plan generation completed successfully ---")
            return simplified_response
        except Exception as e:
            logger.warning(f"Failed to parse AI response: {str(e)}")
            logger.warning("Falling back to simple meal plan generation")
            return self._create_fallback_response(request, f"Parsing error: {str(e)}")
    
    def _create_simplified_meal(self, original_meal: MealDto) -> MealDto:
        """Create a simplified meal with only the name field"""
        return MealDto(name=original_meal.name)
    
    def _simplify_response_meals(self, response: AiMealPlanGenerationResponse) -> AiMealPlanGenerationResponse:
        """Simplify all meals in the response to only include names"""
        simplified_plans = []
        
        for plan in response.generated_plans:
            simplified_plan_meals = []
            for plan_meal in plan.plan_meals:
                simplified_meal = self._create_simplified_meal(plan_meal.meal)
                simplified_plan_meal = PlanMealDto(
                    meal=simplified_meal,
                    required_servings=plan_meal.required_servings
                )
                simplified_plan_meals.append(simplified_plan_meal)
            
            simplified_plan = PlanDto(
                date=plan.date,
                planMeals=simplified_plan_meals
            )
            simplified_plans.append(simplified_plan)
        
        return AiMealPlanGenerationResponse(
            generatedPlans=simplified_plans,
            reasoning=response.reasoning
        )
    
    def _create_fallback_response(self, request: AiMealPlanGenerationRequest, error: str) -> AiMealPlanGenerationResponse:
        """Create a fallback response if AI generation fails"""
        logger.info("--- Creating fallback meal plan ---")
        logger.info(f"Fallback reason: {error}")
        
        generated_plans = []
        
        # Generate simple plans using available meals
        available_meals = request.available_meals
        if available_meals:
            logger.info(f"Creating fallback plan with {len(available_meals)} available meals")
            current_date = request.week_start_date
            meal_index = 0
            
            while current_date <= request.week_end_date:
                original_meal = available_meals[meal_index % len(available_meals)]
                simplified_meal = self._create_simplified_meal(original_meal)
                plan_meal = PlanMealDto(
                    meal=simplified_meal,
                    required_servings=original_meal.serves or 4
                )
                plan = PlanDto(
                    date=current_date,
                    plan_meals=[plan_meal]
                )
                generated_plans.append(plan)
                logger.debug(f"Added fallback plan for {current_date}: {simplified_meal.name}")
                
                current_date = date.fromordinal(current_date.toordinal() + 1)
                meal_index += 1
        else:
            logger.warning("No available meals provided for fallback plan")
        
        logger.info(f"Generated {len(generated_plans)} fallback plans")
        logger.info("--- Fallback meal plan completed ---")
        
        return AiMealPlanGenerationResponse(
            generated_plans=generated_plans,
            reasoning=f"Fallback meal plan generated due to AI parsing error: {error}. Created simple rotation of available meals."
        )