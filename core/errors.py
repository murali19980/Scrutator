"""
User-friendly error messages and error handling utilities.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Mapping of error types to user-friendly messages
ERROR_MESSAGES = {
    "API_KEY_MISSING": {
        "message": "Missing API key. Please set OPENROUTER_API_KEY in your .env file.",
        "suggestion": "Sign up at https://openrouter.ai to get a free API key."
    },
    "RATE_LIMIT": {
        "message": "You've hit the rate limit for this API. Please wait a few minutes.",
        "suggestion": "Consider using a different model or wait and retry."
    },
    "SEARCH_FAILED": {
        "message": "Search failed due to a network issue or API error.",
        "suggestion": "Check your internet connection and try again."
    },
    "NO_PAPERS_FOUND": {
        "message": "No academic papers found for your query.",
        "suggestion": "Try broadening your search terms or using different keywords."
    },
    "PDF_DOWNLOAD_FAILED": {
        "message": "Could not download or parse the PDF file.",
        "suggestion": "Check the DOI or try uploading the PDF manually."
    },
    "SCORING_FAILED": {
        "message": "Paper scoring failed due to an error with the AI model.",
        "suggestion": "Try using a different model or retry later."
    },
    "SYNTHESIS_FAILED": {
        "message": "Failed to synthesize findings from the papers.",
        "suggestion": "Try reducing the number of papers or using a more powerful model."
    },
    "CANCELLED": {
        "message": "Research was cancelled by the user.",
        "suggestion": "You can start a new research task anytime."
    },
    "TIMEOUT": {
        "message": "Research took too long and timed out.",
        "suggestion": "Try a more specific query or reduce the number of papers."
    },
    "CORE_API_KEY_MISSING": {
        "message": "CORE API key is required for PDF fallback.",
        "suggestion": "Set CORE_API_KEY in your .env file or sign up at https://core.ac.uk."
    }
}


def get_user_friendly_error(error_type: str) -> Dict[str, str]:
    """Get user-friendly error message and suggestion."""
    return ERROR_MESSAGES.get(error_type, {
        "message": "An unexpected error occurred.",
        "suggestion": "Please try again or contact support."
    })


class ErrorFormatter:
    """Format errors into user-friendly messages."""
    
    @staticmethod
    def format(error_type: str, details: Optional[Dict] = None) -> str:
        """Format an error into a user-friendly message."""
        error_info = get_user_friendly_error(error_type)
        message = f"❌ {error_info['message']}"
        if details:
            message += f"\n\nDetails: {details}"
        message += f"\n\n💡 {error_info['suggestion']}"
        return message
    
    @staticmethod
    def format_exception(e: Exception) -> str:
        """Format an exception into a user-friendly message."""
        # Try to match the exception to a known error type
        error_type = "UNKNOWN"
        e_str = str(e).lower()
        if "api key" in e_str or "unauthorized" in e_str:
            error_type = "API_KEY_MISSING"
        elif "rate" in e_str or "429" in e_str or "limit" in e_str:
            error_type = "RATE_LIMIT"
        elif "timeout" in e_str:
            error_type = "TIMEOUT"
        elif "no results" in e_str or "no papers" in e_str:
            error_type = "NO_PAPERS_FOUND"
        
        return ErrorFormatter.format(error_type, {"error": str(e)})
