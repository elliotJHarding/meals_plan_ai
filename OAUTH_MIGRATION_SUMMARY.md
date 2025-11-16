# OAuth Authentication Migration Summary

## Overview
Successfully converted the Meal Plan AI API from using a single developer API key to per-user OAuth 2.0 authentication.

## What Changed

### 1. New File: `auth_utils.py`
Created authentication utilities:
- `extract_bearer_token(request)` - Extracts and validates Bearer tokens from Authorization header
- `create_llm_with_token(access_token, model, temperature)` - Creates LLM instances with user OAuth credentials
- `get_optional_token(request)` - Optional token extraction (returns None if missing)

### 2. Updated Services
**All services now require OAuth tokens for AI operations:**

#### `IngredientService` (`ingredient_service.py`)
- Removed hardcoded API key from `__init__`
- Added `_get_llm(access_token)` method
- Updated `get_ingredient_metadata(request, access_token)` to accept token parameter

#### `MealPlanService` (`meal_plan_service.py`)
- Removed hardcoded API key from `__init__`
- Added `_get_llm(access_token)` method
- Updated `generate_meal_plan(request, access_token)` to accept token parameter

#### `MealPlanChatService` (`meal_plan_chat_service.py`)
- Removed hardcoded API key from `__init__`
- Added `_get_llm(access_token)` method
- Updated `suggest_meals_for_day(request, access_token)` to accept token parameter

#### `RecipeService` (`recipe_service.py`)
- No changes needed (doesn't use AI/LLM)

### 3. Updated Endpoints (`main.py`)
**Modified three endpoints to require OAuth authentication:**

#### `/ingredient-metadata` (POST)
- Extracts Bearer token from Authorization header
- Passes token to `ingredient_service.get_ingredient_metadata()`
- Returns 401 if authentication fails

#### `/chat-meal-plan-day` (POST)
- Extracts Bearer token from Authorization header
- Passes token to `meal_plan_chat_service.suggest_meals_for_day()`
- Returns 401 if authentication fails

#### `/generate-meal-plan` (POST)
- Extracts Bearer token from Authorization header
- Passes token to `meal_plan_service.generate_meal_plan()`
- Returns 401 if authentication fails

**Other endpoints remain unchanged:**
- `/` (GET) - No auth required
- `/parse-recipe` (POST) - No auth required (web scraping only)
- `/parse-ingredient` (POST) - No auth required (rule-based parsing)

### 4. Updated Documentation
- `CLAUDE.md` - Added comprehensive OAuth authentication documentation
- Includes examples, error codes, and usage instructions

### 5. Test Files
- `test_oauth_auth.py` - Test suite for OAuth authentication
- Tests missing auth, invalid format, and valid token scenarios

## How to Use

### For API Clients

#### 1. Obtain a Google OAuth 2.0 Access Token
Users must authenticate with Google and obtain an access token with Gemini API permissions.

**Using OAuth Playground (for testing):**
1. Go to https://developers.google.com/oauthplayground/
2. Configure to use your OAuth credentials
3. Select appropriate Google AI APIs
4. Authorize and get the access token

**In Production:**
Implement proper OAuth 2.0 flow in your frontend application.

#### 2. Include Token in Requests
Add the token to the Authorization header:

```bash
curl -X POST http://127.0.0.1:8000/chat-meal-plan-day \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d @test_chat.json
```

#### 3. Handle Authentication Errors
- **401 Unauthorized**: Token is missing, invalid, or expired
  - Prompt user to re-authenticate
  - Refresh the access token if using refresh tokens

### For Development

#### Running the Server
```bash
uvicorn main:app --reload
```

#### Testing Authentication
```bash
# Run basic auth tests (no real token needed)
python test_oauth_auth.py

# Test with real token (edit script first)
# 1. Get token from OAuth Playground
# 2. Edit test_oauth_auth.py
# 3. Uncomment test calls at bottom
# 4. Run script
```

#### Testing Endpoints
```bash
# Without auth (should fail with 401)
curl -X POST http://127.0.0.1:8000/ingredient-metadata \
  -H "Content-Type: application/json" \
  -d '{"ingredient_name": "flour"}'

# With auth (should work if token is valid)
curl -X POST http://127.0.0.1:8000/ingredient-metadata \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ingredient_name": "flour"}'
```

## Authentication Flow

```
Client Request
    ↓
[Authorization: Bearer <token>]
    ↓
FastAPI Endpoint Handler
    ↓
extract_bearer_token(request)
    ↓
[Validate token format]
    ↓
Pass token to Service Method
    ↓
Service creates LLM with create_llm_with_token()
    ↓
[Google OAuth2Credentials created]
    ↓
LLM invokes Google Gemini API
    ↓
[Uses user's token & quota]
    ↓
Return Response
```

## Error Handling

### 401 Unauthorized
**Causes:**
- Missing Authorization header
- Invalid header format (not "Bearer <token>")
- Empty token
- Invalid or expired OAuth token

**Response Example:**
```json
{
  "detail": "Missing Authorization header. Please provide a Bearer token."
}
```

### 500 Internal Server Error
**Causes:**
- API errors (non-auth related)
- Service failures
- Parsing errors

**Response Example:**
```json
{
  "detail": "Failed to generate meal suggestions: <error details>"
}
```

## Benefits of OAuth Authentication

1. **Per-User Quotas**: Each user uses their own Google API quota
2. **Better Security**: No shared API key to protect
3. **User Attribution**: Track API usage per user
4. **Cost Management**: Users responsible for their own API costs
5. **Scalability**: No single API key rate limit bottleneck

## Migration Checklist for Frontend

- [ ] Implement Google OAuth 2.0 flow
- [ ] Store access tokens securely (e.g., httpOnly cookies)
- [ ] Include token in Authorization header for all AI endpoints
- [ ] Handle 401 errors (token refresh or re-authentication)
- [ ] Update API client to add Authorization header
- [ ] Test with real OAuth tokens
- [ ] Update user documentation

## Environment Variables

### No Longer Used (for production):
- `GOOGLE_API_KEY` - Previously used shared API key

### Can Keep (optional, for development):
- `GOOGLE_API_KEY` - Can be used for local testing if you modify the code to fall back to it

## Backwards Compatibility

⚠️ **BREAKING CHANGE**: This is a breaking change. All AI-powered endpoints now require OAuth authentication.

**Migration Path:**
1. Frontend must implement OAuth flow
2. Update all API calls to include Authorization header
3. Test thoroughly before deploying
4. Consider gradual rollout or feature flag

## Testing Recommendations

1. **Unit Tests**: Test `extract_bearer_token()` with various inputs
2. **Integration Tests**: Test each endpoint with valid/invalid tokens
3. **End-to-End Tests**: Test full OAuth flow from frontend to backend
4. **Load Tests**: Verify performance with OAuth token validation
5. **Security Tests**: Attempt auth bypass, token injection, etc.

## Troubleshooting

### Issue: "401 Unauthorized" with valid token
**Solutions:**
- Verify token hasn't expired (tokens typically expire after 1 hour)
- Check token has correct API permissions
- Ensure token is properly formatted in header
- Check for extra spaces or newlines in token

### Issue: "Invalid or expired OAuth token"
**Solutions:**
- Refresh the access token using refresh token
- Re-authenticate user
- Verify OAuth client credentials are correct

### Issue: Import errors
**Solutions:**
- Ensure `auth_utils.py` is in the project root
- Check all service files import `create_llm_with_token`
- Verify main.py imports `extract_bearer_token`

## Next Steps

1. **Implement Frontend OAuth**: Add Google OAuth 2.0 to your frontend
2. **Token Refresh**: Implement token refresh logic
3. **Rate Limiting**: Add per-user rate limiting based on OAuth token
4. **Monitoring**: Track API usage per user
5. **Documentation**: Update API documentation with auth requirements
6. **User Guide**: Create guide for users on obtaining API access

## Files Changed

```
Modified:
  - main.py (updated 3 endpoints)
  - ingredient_service.py (OAuth support)
  - meal_plan_service.py (OAuth support)
  - meal_plan_chat_service.py (OAuth support)
  - CLAUDE.md (documentation)

Created:
  - auth_utils.py (authentication utilities)
  - test_oauth_auth.py (test suite)
  - OAUTH_MIGRATION_SUMMARY.md (this file)

Unchanged:
  - recipe_service.py (no AI/LLM usage)
  - models.py (no changes needed)
```

## Questions?

Refer to:
- `CLAUDE.md` - General project documentation
- `auth_utils.py` - Authentication implementation
- `test_oauth_auth.py` - Example usage
- Google OAuth 2.0 docs: https://developers.google.com/identity/protocols/oauth2
