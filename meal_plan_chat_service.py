import os
import json
import logging
from datetime import date
from typing import List
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from meals_contract.models.day_meal_plan_chat_request import DayMealPlanChatRequest
from meals_contract.models.day_meal_plan_chat_response import DayMealPlanChatResponse
from meals_contract.models.suggested_meal import SuggestedMeal
from meals_contract.models.meal_dto import MealDto
from meals_contract.models.calendar_event_dto import CalendarEventDto
from meals_contract.models.plan_dto import PlanDto
from meals_contract.models.chat_message import ChatMessage

from meals_contract.models import *
from auth_utils import create_llm_with_token

load_dotenv()

logger = logging.getLogger(__name__)


class MealPlanChatService:
    def __init__(self):
        self.output_parser = PydanticOutputParser(pydantic_object=DayMealPlanChatResponse)

    def _get_llm(self, access_token: str) -> ChatGoogleGenerativeAI:
        """Create LLM instance with user's OAuth token"""
        return create_llm_with_token(
            access_token=access_token,
            model="gemini-flash-latest",
            temperature=0.7
        )

    def suggest_meals_for_day(
        self,
        request: DayMealPlanChatRequest,
        access_token: str
    ) -> DayMealPlanChatResponse:
        """
        Generate meal suggestions for a specific day based on context and conversation history.
        Returns 3-5 ranked meal suggestions with reasoning.

        Args:
            request: The meal plan chat request
            access_token: User's OAuth access token for Google Gemini API

        Returns:
            DayMealPlanChatResponse with meal suggestions
        """
        logger.info(f"--- Starting day meal plan chat for {request.day_of_week} ---")

        # Determine if this is an initial request or follow-up
        is_initial_request = len(request.conversation_history) == 1

        if is_initial_request:
            logger.info("Initial request - generating first suggestions")
            prompt = self._create_initial_prompt(request)
        else:
            logger.info(f"Follow-up request - conversation has {len(request.conversation_history)} messages")
            prompt = self._create_followup_prompt(request)

        # Generate the response
        logger.info("Creating LLM with user's OAuth token...")
        try:
            llm = self._get_llm(access_token)
            logger.info("Calling Google Generative AI...")
            response = llm.invoke(prompt)
            logger.info(f"Received AI response (length: {len(response.content)} chars)")
            logger.debug(f"Raw AI response:\n{response.content}")
        except Exception as e:
            logger.error(f"Error calling AI model: {str(e)}")
            return self._create_fallback_response(request, f"AI model error: {str(e)}")

        # Parse the response
        try:
            logger.info("Parsing AI response...")
            parsed_response = self.output_parser.parse(response.content)

            # Ensure we have 3-5 suggestions
            if len(parsed_response.suggestions) < 3:
                logger.warning(f"Only {len(parsed_response.suggestions)} suggestions returned, expected 3-5")
            elif len(parsed_response.suggestions) > 5:
                logger.warning(f"{len(parsed_response.suggestions)} suggestions returned, trimming to 5")
                parsed_response.suggestions = parsed_response.suggestions[:5]

            logger.info(f"Successfully parsed response with {len(parsed_response.suggestions)} suggestions")
            logger.info("--- Day meal plan chat completed successfully ---")
            return parsed_response
        except Exception as e:
            logger.warning(f"Failed to parse AI response: {str(e)}")
            logger.warning("Falling back to simple suggestions")
            return self._create_fallback_response(request, f"Parsing error: {str(e)}")

    def _create_initial_prompt(self, request: DayMealPlanChatRequest) -> str:
        """Create the prompt for initial meal suggestions"""

        # Format day info
        day_name = request.day_of_week.strftime("%A, %B %d, %Y")

        # Format calendar events
        event_summaries = []
        for event in request.calendar_events:
            event_summaries.append(f"- {event.name} at {event.time} ({'All day' if event.all_day else 'Timed event'})")
        events_text = "\n".join(event_summaries) if event_summaries else "No calendar events"

        # Format already planned meals for the week
        planned_meals_text = self._format_current_week_plan(request.current_week_plan, request.day_of_week)

        # Format recent meal history
        recent_meals_text = self._format_recent_meals(request.recent_meal_plans)

        # Format available meals
        available_meals_text = self._format_available_meals(request.available_meals)

        # Format chat context
        chat_context_text = self._format_chat_context(request.chat_context)

        prompt_template = ChatPromptTemplate.from_template("""
You are a helpful meal planning assistant. Your task is to suggest 3-5 meals for a specific day based on the user's context.

DAY BEING PLANNED:
{day_name}

USER CONTEXT (persistent information about the user):
{chat_context}

CALENDAR EVENTS FOR THIS DAY:
{events}

ALREADY PLANNED MEALS THIS WEEK:
{planned_meals}

RECENT MEAL HISTORY (to avoid repetition):
{recent_meals}

AVAILABLE MEALS TO CHOOSE FROM:
{available_meals}

INSTRUCTIONS:
- Suggest 3-5 meals ranked from most suitable to least suitable
- ALWAYS consider the user context when making suggestions (dietary restrictions, preferences, household info, etc.)
- Consider the calendar events when choosing effort levels:
  * Busy days with many events → suggest LOW effort meals
  * Free days → can suggest MEDIUM or HIGH effort meals
  * Consider event timings (morning events less likely to affect dinner)
- Avoid suggesting meals that were recently planned (check recent history)
- Ensure variety - don't suggest similar meals (e.g., multiple pasta dishes)
- Consider the already planned meals for this week to ensure variety
- For each suggestion, assign a rank (1-5) where 1 is most suitable
- Provide clear reasoning explaining why these meals are appropriate for this day

CONTEXT MANAGEMENT:
- If the user's message contains important information that should be remembered for future meal planning, include it in the 'updated_chat_context' field
- Important information includes: dietary restrictions, preferences, dislikes, household composition, timing preferences, allergies, favorite meals, etc.
- If no new important information is provided, set 'updated_chat_context' to null
- If updating context, include ALL previous context plus the new information (don't remove existing context)

RESPONSE FORMAT:
{format_instructions}

Remember to suggest 3-5 meals, ranked by suitability, with a single reasoning paragraph explaining your choices.
""")

        prompt = prompt_template.format(
            day_name=day_name,
            chat_context=chat_context_text,
            events=events_text,
            planned_meals=planned_meals_text,
            recent_meals=recent_meals_text,
            available_meals=available_meals_text,
            format_instructions=self.output_parser.get_format_instructions()
        )

        logger.debug(f"Created initial prompt (length: {len(prompt)} chars)")
        return prompt

    def _create_followup_prompt(self, request: DayMealPlanChatRequest) -> str:
        """Create the prompt for follow-up conversation with user feedback"""

        # Get the last user message (most recent feedback)
        last_user_message = None
        for msg in reversed(request.conversation_history):
            if msg.role == "user":
                last_user_message = msg.content
                break

        # Format conversation history
        conversation_text = "\n".join([
            f"{msg.role.upper()}: {msg.content}"
            for msg in request.conversation_history
        ])

        # Format day info
        day_name = request.day_of_week.strftime("%A, %B %d, %Y")

        # Format chat context
        chat_context_text = self._format_chat_context(request.chat_context)

        # Format calendar events
        event_summaries = []
        for event in request.calendar_events:
            event_summaries.append(f"- {event.name} at {event.time} ({'All day' if event.all_day else 'Timed event'})")
        events_text = "\n".join(event_summaries) if event_summaries else "No calendar events"

        # Format already planned meals for the week
        planned_meals_text = self._format_current_week_plan(request.current_week_plan, request.day_of_week)

        # Format recent meal history
        recent_meals_text = self._format_recent_meals(request.recent_meal_plans)

        # Format available meals
        available_meals_text = self._format_available_meals(request.available_meals)

        prompt_template = ChatPromptTemplate.from_template("""
You are a helpful meal planning assistant. You previously suggested meals for {day_name}, and the user has provided feedback.

USER CONTEXT (persistent information about the user):
{chat_context}

CALENDAR EVENTS FOR THIS DAY:
{events}

ALREADY PLANNED MEALS THIS WEEK:
{planned_meals}

RECENT MEAL HISTORY (to avoid repetition):
{recent_meals}

CONVERSATION HISTORY:
{conversation}

AVAILABLE MEALS TO CHOOSE FROM:
{available_meals}

USER'S LATEST FEEDBACK:
{user_feedback}

INSTRUCTIONS:
- Based on the user's feedback, adjust your meal suggestions
- ALWAYS consider the user context when making suggestions (dietary restrictions, preferences, household info, etc.)
- Consider the calendar events when choosing effort levels:
  * Busy days with many events → suggest LOW effort meals
  * Free days → can suggest MEDIUM or HIGH effort meals
  * Consider event timings (morning events less likely to affect dinner)
- Avoid suggesting meals that were recently planned (check recent history)
- Consider the already planned meals for this week to ensure variety
- Still suggest 3-5 meals ranked by suitability
- Address the user's specific requests or concerns
- If the user wants vegetarian meals, only suggest vegetarian options
- If the user doesn't like a specific ingredient or meal type, exclude those
- If the user likes one of your suggestions, you can keep it and suggest variations
- Provide clear reasoning explaining how you addressed their feedback

CONTEXT MANAGEMENT:
- If the user's feedback contains important information that should be remembered for future meal planning, include it in the 'updated_chat_context' field
- Important information includes: dietary restrictions, preferences, dislikes, household composition, timing preferences, allergies, favorite meals, etc.
- If no new important information is provided, set 'updated_chat_context' to null
- If updating context, include ALL previous context plus the new information (don't remove existing context)

RESPONSE FORMAT:
{format_instructions}

Remember to suggest 3-5 meals, ranked by suitability, with reasoning that addresses the user's feedback.
""")

        prompt = prompt_template.format(
            day_name=day_name,
            chat_context=chat_context_text,
            events=events_text,
            planned_meals=planned_meals_text,
            recent_meals=recent_meals_text,
            conversation=conversation_text,
            available_meals=available_meals_text,
            user_feedback=last_user_message or "No specific feedback",
            format_instructions=self.output_parser.get_format_instructions()
        )

        logger.debug(f"Created follow-up prompt (length: {len(prompt)} chars)")
        return prompt

    def _format_current_week_plan(self, current_week_plan: List[PlanDto], current_day: date) -> str:
        """Format the current week's meal plan, highlighting already planned meals"""
        if not current_week_plan:
            return "No meals planned for this week yet"

        lines = []
        for plan in current_week_plan:
            if plan.var_date == current_day:
                continue  # Skip the day we're planning

            meal_names = [pm.meal.name for pm in (plan.plan_meals or [])]
            if meal_names:
                lines.append(f"- {plan.var_date.strftime('%A, %b %d')}: {', '.join(meal_names)}")

        return "\n".join(lines) if lines else "No other meals planned for this week"

    def _format_recent_meals(self, recent_meal_plans: List[PlanDto]) -> str:
        """Format recent meal history to avoid repetition"""
        if not recent_meal_plans:
            return "No recent meal history available"

        # Get unique meals from recent plans
        recent_meals = set()
        for plan in recent_meal_plans[-20:]:  # Last 20 days
            for plan_meal in (plan.plan_meals or []):
                recent_meals.add(plan_meal.meal.name)

        if not recent_meals:
            return "No recent meals to avoid"

        return "Recently planned meals (try to avoid): " + ", ".join(sorted(recent_meals))

    def _format_available_meals(self, available_meals: List[MealDto]) -> str:
        """Format available meals with their attributes"""
        lines = []
        for meal in available_meals:
            effort_str = meal.effort.value if meal.effort else 'Unknown'
            tags_str = ""
            if meal.tags:
                tag_values = []
                for tag in meal.tags:
                    if hasattr(tag, 'value'):
                        tag_values.append(tag.value)
                    else:
                        tag_values.append(str(tag))
                tags_str = f" [Tags: {', '.join(tag_values)}]"

            lines.append(
                f"- {meal.name} [ID: {meal.id}] (Effort: {effort_str}, Serves: {meal.serves or 'N/A'}, "
                f"Prep: {meal.prep_time_minutes or 'N/A'}min){tags_str}"
            )

        return "\n".join(lines)

    def _format_chat_context(self, chat_context: dict) -> str:
        """Format chat context dictionary into a readable string"""
        if not chat_context:
            return "No stored context yet - this is the first interaction or no preferences have been captured"

        lines = []
        for key, value in chat_context.items():
            # Format the key to be more readable (e.g., dietary_restrictions -> Dietary Restrictions)
            formatted_key = key.replace('_', ' ').title()

            # Handle different value types
            if isinstance(value, list):
                value_str = ", ".join(str(v) for v in value)
            elif isinstance(value, dict):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            lines.append(f"- {formatted_key}: {value_str}")

        return "\n".join(lines)

    def _create_fallback_response(self, request: DayMealPlanChatRequest, error: str) -> DayMealPlanChatResponse:
        """Create a fallback response if AI generation fails"""
        logger.info("--- Creating fallback meal suggestions ---")
        logger.info(f"Fallback reason: {error}")

        # Simple fallback: suggest first 3-5 available meals
        suggestions = []
        available_meals = request.available_meals[:5]  # Take up to 5 meals

        for i, meal in enumerate(available_meals):
            suggestions.append(SuggestedMeal(
                meal_name=meal.name,
                meal_id=meal.id or 0,  # Use 0 if id is None
                rank=i + 1,
                suitability_score=None
            ))

        logger.info(f"Generated {len(suggestions)} fallback suggestions")
        logger.info("--- Fallback suggestions completed ---")

        return DayMealPlanChatResponse(
            suggestions=suggestions,
            reasoning=f"I encountered an error generating personalized suggestions ({error}). Here are some meal options from your available meals.",
            conversation_complete=False
        )
