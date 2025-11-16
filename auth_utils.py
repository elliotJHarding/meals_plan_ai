import logging
from typing import Optional
from fastapi import HTTPException, Request
from langchain_google_genai import ChatGoogleGenerativeAI
from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as OAuth2Credentials

logger = logging.getLogger(__name__)


def extract_bearer_token(request: Request) -> str:
    """
    Extract and validate Bearer token from Authorization header.

    Args:
        request: FastAPI Request object

    Returns:
        str: The OAuth access token

    Raises:
        HTTPException: 401 if token is missing or malformed
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        logger.warning("Missing Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header. Please provide a Bearer token."
        )

    # Check if it's a Bearer token
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(f"Malformed Authorization header: {auth_header}")
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'"
        )

    access_token = parts[1]

    if not access_token:
        logger.warning("Empty access token")
        raise HTTPException(
            status_code=401,
            detail="Empty access token provided"
        )

    logger.info(f"Successfully extracted Bearer token (length: {len(access_token)})")
    return access_token


def create_llm_with_token(
    access_token: str,
    model: str = "gemini-flash-latest",
    temperature: float = 0.7
) -> ChatGoogleGenerativeAI:
    """
    Create a ChatGoogleGenerativeAI instance using a user's OAuth access token.

    Args:
        access_token: Google OAuth2 access token
        model: Model name (default: gemini-pro)
        temperature: Temperature setting (default: 0.7)

    Returns:
        ChatGoogleGenerativeAI: Initialized LLM instance

    Raises:
        HTTPException: 401 if token is invalid or authentication fails
    """
    try:
        logger.info(f"Creating LLM instance with model: {model}, temperature: {temperature}")

        # Create OAuth2 credentials from the access token
        credentials = OAuth2Credentials(token=access_token)

        # Initialize the LLM with the user's credentials
        llm = ChatGoogleGenerativeAI(
            model=model,
            credentials=credentials,
            temperature=temperature
        )

        logger.info("Successfully created LLM instance with OAuth credentials")
        return llm

    except Exception as e:
        logger.error(f"Failed to create LLM with OAuth token: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired OAuth token: {str(e)}"
        )


def get_optional_token(request: Request) -> Optional[str]:
    """
    Extract Bearer token from Authorization header if present.
    Returns None if not present (no exception).

    Args:
        request: FastAPI Request object

    Returns:
        Optional[str]: The OAuth access token or None
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1] if parts[1] else None
