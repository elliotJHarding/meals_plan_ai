# Chat Context Feature Documentation

## Overview

The Chat Context feature enables persistent storage of user-specific information across meal planning conversations. This allows the AI to remember important details like dietary restrictions, preferences, and household information to provide more personalized meal suggestions over time.

## How It Works

### 1. **Request Flow**
- Client sends a `DayMealPlanChatRequest` with an optional `chatContext` field
- The context is included in the LLM prompt
- The LLM uses this context to personalize meal suggestions

### 2. **Response Flow**
- The LLM analyzes the user's messages for important information
- If new preferences/restrictions are mentioned, the LLM returns `updatedChatContext`
- Client persists the updated context to the database
- Next request includes the updated context

### 3. **Context Lifecycle**
```
Initial Request (no context)
    ↓
User: "I'm vegetarian and have 2 kids"
    ↓
LLM Response includes: updatedChatContext: {
    "dietary_restrictions": ["vegetarian"],
    "household_size": 4,
    "has_children": true
}
    ↓
Client saves to database
    ↓
Next Request includes saved context
    ↓
LLM uses context for better suggestions
```

## API Changes

### Request Model (`DayMealPlanChatRequest`)

**New Field:**
```python
chat_context: Optional[dict] = Field(
    None,
    alias="chatContext",
    description="Persistent context about user preferences and important information for meal planning"
)
```

**Example:**
```json
{
  "dayOfWeek": 1735689600000,
  "calendarEvents": [],
  "availableMeals": [...],
  "conversationHistory": [...],
  "chatContext": {
    "dietary_restrictions": ["vegetarian", "no nuts"],
    "household_size": 4,
    "has_children": true,
    "preferred_cuisines": ["Italian", "Mexican"],
    "dislikes": ["mushrooms", "olives"],
    "cooking_skill": "intermediate",
    "weekday_preference": "quick meals on weekdays"
  }
}
```

### Response Model (`DayMealPlanChatResponse`)

**New Field:**
```python
updated_chat_context: Optional[dict] = Field(
    None,
    alias="updatedChatContext",
    description="Modified context if the LLM identified important information to remember"
)
```

**Example:**
```json
{
  "suggestions": [...],
  "reasoning": "...",
  "conversationComplete": false,
  "updatedChatContext": {
    "dietary_restrictions": ["vegetarian", "no nuts", "lactose intolerant"],
    "household_size": 4,
    "has_children": true,
    "preferred_cuisines": ["Italian", "Mexican"],
    "dislikes": ["mushrooms", "olives"],
    "cooking_skill": "intermediate",
    "weekday_preference": "quick meals on weekdays",
    "spice_preference": "mild"
  }
}
```

## What Gets Stored in Context?

The LLM identifies and stores information such as:

1. **Dietary Information**
   - Restrictions (vegetarian, vegan, gluten-free, etc.)
   - Allergies (nuts, shellfish, dairy, etc.)
   - Preferences (no spicy food, loves pasta, etc.)

2. **Household Information**
   - Number of people
   - Presence of children
   - Age groups (toddlers, teenagers, etc.)

3. **Cooking Preferences**
   - Skill level (beginner, intermediate, advanced)
   - Time preferences (quick meals on weekdays, etc.)
   - Equipment availability

4. **Taste Preferences**
   - Favorite cuisines
   - Disliked ingredients or meals
   - Spice tolerance

5. **Schedule & Lifestyle**
   - Meal timing preferences
   - Prep time constraints
   - Batch cooking preferences

## Implementation Guidelines

### Backend (Database)

Store the context as a JSON field associated with each user:

```sql
CREATE TABLE user_chat_context (
    user_id INT PRIMARY KEY,
    context JSON NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### Client Usage

1. **First Request** (no context):
```javascript
const response = await fetch('/chat-meal-plan-day', {
  method: 'POST',
  body: JSON.stringify({
    dayOfWeek: Date.now(),
    availableMeals: [...],
    conversationHistory: [],
    chatContext: null  // or omit the field
  })
});
```

2. **Process Response**:
```javascript
const data = await response.json();

// If LLM returned updated context, save it
if (data.updatedChatContext) {
  await saveUserContext(userId, data.updatedChatContext);
}
```

3. **Subsequent Requests** (with context):
```javascript
const savedContext = await getUserContext(userId);

const response = await fetch('/chat-meal-plan-day', {
  method: 'POST',
  body: JSON.stringify({
    dayOfWeek: Date.now(),
    availableMeals: [...],
    conversationHistory: [...],
    chatContext: savedContext  // Include saved context
  })
});
```

## Context Update Logic

The LLM follows these rules for updating context:

1. **Incremental Updates**: New information is ADDED to existing context, not replaced
2. **Override Existing**: If user corrects previous information, it replaces the old value
3. **Null for No Changes**: If no new important information is detected, `updatedChatContext` is `null`
4. **Complete Context**: The LLM returns the FULL context (old + new), not just changes

## Testing

Test files are provided:

1. **`test_chat_with_context.json`** - Initial request with context
2. **`test_chat_followup_with_context.json`** - Follow-up with conversation history

Test the endpoint:
```bash
# Start the server
uvicorn main:app --reload

# Test with context
curl -X POST http://127.0.0.1:8000/chat-meal-plan-day \
  -H "Content-Type: application/json" \
  -d @test_chat_with_context.json
```

## Benefits

1. **Personalization**: Meal suggestions become more relevant over time
2. **Efficiency**: Users don't need to repeat preferences in every conversation
3. **Better UX**: The AI "remembers" important details
4. **Flexibility**: Context is a dictionary, so new fields can be added without schema changes
5. **Transparency**: Users can see and edit their stored context

## Best Practices

1. **Privacy**: Store context securely and allow users to view/edit/delete it
2. **Validation**: Sanitize context data before storing in database
3. **Size Limits**: Implement reasonable size limits for context (e.g., 10KB max)
4. **Versioning**: Consider adding a version field if context structure evolves
5. **User Control**: Provide UI for users to manage their context

## Example Conversation Flow

**Turn 1:**
- User: "Suggest meals for tonight"
- Context: `null`
- Response: Generic suggestions based on available meals
- Updated Context: `null` (no new info)

**Turn 2:**
- User: "I'm vegetarian and allergic to nuts"
- Context: `null`
- Response: Vegetarian suggestions without nuts
- Updated Context: `{"dietary_restrictions": ["vegetarian", "no nuts"]}`

**Turn 3:**
- User: "What about tomorrow? I have a busy day"
- Context: `{"dietary_restrictions": ["vegetarian", "no nuts"]}`
- Response: Quick, vegetarian meals without nuts
- Updated Context: `{"dietary_restrictions": ["vegetarian", "no nuts"], "weekday_preference": "quick meals when busy"}`

**Turn 4 (next week):**
- User: "Suggest meals for Monday"
- Context: `{"dietary_restrictions": ["vegetarian", "no nuts"], "weekday_preference": "quick meals when busy"}`
- Response: Automatically considers vegetarian, nut-free, quick meals
- Updated Context: `null` (no new info)
