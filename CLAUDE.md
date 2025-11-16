# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
uvicorn main:app --reload
```
This starts the FastAPI application on http://127.0.0.1:8000 with hot reload enabled.

### Testing Endpoints
Use the provided `test_main.http` file with an HTTP client (like REST Client in VS Code or IntelliJ) to test the API endpoints:
- GET http://127.0.0.1:8000/ - Returns hello world message
- GET http://127.0.0.1:8000/hello/{name} - Returns personalized greeting

## Authentication

### OAuth 2.0 Authentication
**IMPORTANT**: All AI-powered endpoints require OAuth 2.0 authentication with a Google access token.

#### Endpoints Requiring Authentication:
- `POST /chat-meal-plan-day` - Chat-based meal planning
- `POST /generate-meal-plan` - Weekly meal plan generation
- `POST /ingredient-metadata` - AI-powered ingredient classification

#### How to Authenticate:
Include the Google OAuth 2.0 access token in the Authorization header:

```http
Authorization: Bearer <your_google_oauth_token>
```

#### Example Request:
```bash
curl -X POST http://127.0.0.1:8000/chat-meal-plan-day \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..." \
  -H "Content-Type: application/json" \
  -d @test_chat.json
```

#### Obtaining an OAuth Token:
Users must authenticate with Google OAuth 2.0 and obtain an access token with permissions to use the Google Gemini API. The token is used to:
- Authenticate the user's identity
- Use their Google Gemini API quota
- Track API usage per user

#### Authentication Errors:
- **401 Unauthorized**: Missing or invalid OAuth token
  - Missing Authorization header
  - Malformed token format
  - Expired or invalid token
- **500 Internal Server Error**: Other errors (check logs)

#### Endpoints NOT Requiring Authentication:
- `GET /` - Health check
- `POST /parse-recipe` - Recipe parsing (web scraping only)
- `POST /parse-ingredient` - Ingredient parsing (rule-based, no AI)

## Project Architecture

This is a FastAPI application for AI-powered meal planning functionality. Contains:

### Core Files:
- `main.py` - FastAPI application entry point with endpoints
- `auth_utils.py` - OAuth authentication utilities
- `models.py` - Pydantic data models
- `meal_plan_service.py` - Weekly meal plan generation service
- `meal_plan_chat_service.py` - Interactive meal planning chat service
- `ingredient_service.py` - Ingredient parsing and classification
- `recipe_service.py` - Recipe parsing from URLs

### Services:
- **MealPlanService**: Generates weekly meal plans using Google Gemini
- **MealPlanChatService**: Interactive day-by-day meal planning with chat context
- **IngredientService**: Parses ingredient strings and classifies storage types
- **RecipeService**: Scrapes and parses recipes from URLs

The project uses:
- **FastAPI** - Web framework for building APIs
- **Uvicorn** - ASGI server for running the application
- **Google Gemini** - AI model for meal planning and classification
- **LangChain** - LLM framework for structured outputs
- **Python 3.9.6** - Runtime environment

## Development Notes

- OAuth authentication is required for all AI-powered endpoints
- Each user's Google OAuth token is used for API calls (not a shared API key)
- Tokens must have permissions for Google Gemini API access
- Users are responsible for their own API quota and billing