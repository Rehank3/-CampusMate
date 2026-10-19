import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current directory and parent directories
env_paths = [
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]
for p in env_paths:
    if p.exists():
        load_dotenv(p)
        break
else:
    load_dotenv()  # Fallback to default search


def get_api_key() -> str | None:
    """Retrieve GEMINI_API_KEY from environment."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return key if key else None


def is_ai_configured() -> bool:
    """Check if Gemini API key is configured."""
    return get_api_key() is not None


def get_gemini_client():
    """Return an initialized Google GenAI client if configured."""
    api_key = get_api_key()
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def explain_assignment(title: str, subject: str, deadline: str) -> dict:
    """Explain core concepts, approach, and pitfalls for an assignment."""
    if not is_ai_configured():
        return {
            "success": False,
            "error": "Gemini API key is not configured on the backend. Please set GEMINI_API_KEY in your .env file.",
        }

    client = get_gemini_client()
    if not client:
        return {
            "success": False,
            "error": "Failed to initialize Gemini API client. Please verify your GEMINI_API_KEY.",
        }

    prompt = f"""You are CampusMate AI, an expert academic advisor for university students.
Please provide a structured, encouraging, and clear guide to help a student succeed in the following assignment:

- **Assignment Title:** {title}
- **Subject / Course:** {subject}
- **Target Deadline:** {deadline}

Structure your response with these clear sections:
1. 🎯 **Core Concept Overview**: What this assignment is fundamentally testing and why it matters in {subject}.
2. 🚀 **Recommended Step-by-Step Approach**: A pragmatic 4-5 step execution workflow.
3. ⚠️ **Common Pitfalls & Mistakes to Avoid**: Pitfalls university students frequently encounter on this topic.
4. 📚 **Key Resources & Reference Topics**: Specific concepts, formulas, or documentation to review.
5. ⏱️ **Estimated Effort & Time Allocation**: Suggested hours and time blocks.

Keep it structured, engaging, and professional."""

    try:
        # Try gemini-2.5-flash with fallback to gemini-1.5-flash
        model_name = "gemini-2.5-flash"
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
        except Exception:
            model_name = "gemini-1.5-flash"
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

        return {
            "success": True,
            "explanation": response.text,
            "model": model_name,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Gemini API error: {str(e)}",
        }


def generate_study_plan(
    title: str,
    subject: str,
    deadline: str,
    daily_hours: float = 2.0,
    student_notes: str = "",
) -> dict:
    """Generate a structured day-by-day revision and study plan."""
    if not is_ai_configured():
        return {
            "success": False,
            "error": "Gemini API key is not configured on the backend. Please set GEMINI_API_KEY in your .env file.",
        }

    client = get_gemini_client()
    if not client:
        return {
            "success": False,
            "error": "Failed to initialize Gemini API client. Please verify your GEMINI_API_KEY.",
        }

    prompt = f"""You are CampusMate AI, a personalized university study planner.
Generate a realistic, high-impact study and preparation schedule for:

- **Assignment / Exam:** {title}
- **Subject:** {subject}
- **Deadline:** {deadline}
- **Available Study Time:** {daily_hours} hours per day
- **Student Notes / Focus Areas:** {student_notes if student_notes else "General comprehensive preparation"}

Please provide:
1. 📋 **Preparation Strategy Summary**: High-level breakdown of the workload.
2. 🗓️ **Day-by-Day Study Schedule**: Specific daily milestones from today until the deadline, including daily focus, key tasks, and active recall practice.
3. 🧠 **Active Learning Techniques**: Recommendations (e.g., Feynman technique, practice problems, flashcards).
4. ✅ **Pre-Submission Checklist**: 3-5 critical items to double-check before submission.

Format with clean Markdown headers, bullet points, and checkboxes."""

    try:
        model_name = "gemini-2.5-flash"
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
        except Exception:
            model_name = "gemini-1.5-flash"
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

        return {
            "success": True,
            "plan": response.text,
            "model": model_name,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Gemini API error: {str(e)}",
        }


def student_chat_assistant(messages: list[dict], context: str = "") -> dict:
    """Conversational university student AI assistant."""
    if not is_ai_configured():
        return {
            "success": False,
            "error": "Gemini API key is not configured on the backend. Please set GEMINI_API_KEY in your .env file.",
        }

    client = get_gemini_client()
    if not client:
        return {
            "success": False,
            "error": "Failed to initialize Gemini API client. Please verify your GEMINI_API_KEY.",
        }

    # Format conversation history
    convo_text = "You are CampusMate AI, a helpful, encouraging university student advisor.\n"
    if context:
        convo_text += f"\nStudent context / current tasks:\n{context}\n"

    convo_text += "\nConversation history:\n"
    for msg in messages:
        role = "Student" if msg.get("role") == "user" else "CampusMate AI"
        convo_text += f"{role}: {msg.get('content')}\n"

    convo_text += "CampusMate AI: "

    try:
        model_name = "gemini-2.5-flash"
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=convo_text,
            )
        except Exception:
            model_name = "gemini-1.5-flash"
            response = client.models.generate_content(
                model=model_name,
                contents=convo_text,
            )

        return {
            "success": True,
            "reply": response.text,
            "model": model_name,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Gemini API error: {str(e)}",
        }
