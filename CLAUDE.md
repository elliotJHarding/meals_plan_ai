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

## Project Architecture

This is a minimal FastAPI application for meal planning AI functionality. Currently contains:

- `main.py` - FastAPI application entry point with basic endpoints
- `test_main.http` - HTTP test file for manual endpoint testing

The project uses:
- **FastAPI** - Web framework for building APIs
- **Uvicorn** - ASGI server for running the application
- **Python 3.9.6** - Runtime environment

## Development Notes

- No testing framework, linting, or code formatting tools are currently configured
- No requirements.txt or dependency management files present
- Project structure is minimal with room for expansion into meal planning features