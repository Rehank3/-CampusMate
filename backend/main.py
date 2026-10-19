from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import uuid

from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from database import AssignmentDB, UPLOADS_DIR, get_db, init_db, migrate_db
from ai_service import (
    explain_assignment as ai_explain,
    generate_study_plan as ai_study_plan,
    is_ai_configured,
    student_chat_assistant,
)
from doc_extractor import extract_text, parse_assignment_details, SUPPORTED_EXTENSIONS, MAX_FILE_SIZE_MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_db()   # safe ALTER TABLE for new columns
    yield


app = FastAPI(title="CampusMate API", lifespan=lifespan)


# ── Pydantic Schemas ────────────────────────────────────────────────────────────

class AssignmentBase(BaseModel):
    title: str
    subject: str
    deadline: str
    priority: str = "Medium"


class AssignmentCreate(AssignmentBase):
    # Optional attachment fields populated from /upload response
    attachment_original_name: Optional[str] = None
    attachment_stored_name: Optional[str] = None
    attachment_mime_type: Optional[str] = None
    extracted_text: Optional[str] = None


# Backward-compatibility alias
Assignment = AssignmentCreate


class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    is_completed: Optional[bool] = None


class AssignmentResponse(AssignmentBase):
    id: int
    is_completed: bool
    created_at: Optional[datetime] = None
    urgency: str
    days_remaining: int
    attachment_original_name: Optional[str] = None
    attachment_stored_name: Optional[str] = None
    attachment_mime_type: Optional[str] = None
    extracted_text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AIExplainRequest(BaseModel):
    title: str
    subject: str
    deadline: str


class AIStudyPlanRequest(BaseModel):
    title: str
    subject: str
    deadline: str
    daily_hours: float = 2.0
    notes: Optional[str] = ""


class AIChatMessage(BaseModel):
    role: str
    content: str


class AIChatRequest(BaseModel):
    messages: List[AIChatMessage]
    context: Optional[str] = ""


# ── Core Endpoints ──────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return {"message": "Welcome to CampusMate!"}


@app.get("/assignments", response_model=List[AssignmentResponse])
def get_assignments(
    status_filter: Optional[str] = Query(None, alias="status"),
    urgency_filter: Optional[str] = Query(None, alias="urgency"),
    db: Session = Depends(get_db),
):
    query = db.query(AssignmentDB)
    if status_filter == "pending":
        query = query.filter(AssignmentDB.is_completed == False)
    elif status_filter == "completed":
        query = query.filter(AssignmentDB.is_completed == True)

    assignments = query.order_by(AssignmentDB.deadline.asc()).all()

    if urgency_filter:
        normalized = urgency_filter.lower().replace("_", " ")
        assignments = [a for a in assignments if a.urgency.lower() == normalized]

    return assignments


@app.get("/assignments/upcoming", response_model=List[AssignmentResponse])
def get_upcoming_deadlines(
    days: int = Query(3, description="Threshold in days to consider as upcoming or urgent"),
    db: Session = Depends(get_db),
):
    """Returns pending assignments that are overdue, due today, or due within the specified days."""
    assignments = (
        db.query(AssignmentDB)
        .filter(AssignmentDB.is_completed == False)
        .order_by(AssignmentDB.deadline.asc())
        .all()
    )
    return [a for a in assignments if a.days_remaining <= days]


@app.get("/assignments/summary")
def get_assignments_summary(db: Session = Depends(get_db)):
    """Returns counts broken down by status and urgency."""
    assignments = db.query(AssignmentDB).all()
    overdue   = sum(1 for a in assignments if a.urgency == "Overdue")
    due_today = sum(1 for a in assignments if a.urgency == "Due Today")
    due_soon  = sum(1 for a in assignments if a.urgency == "Due Soon")
    upcoming  = sum(1 for a in assignments if a.urgency == "Upcoming")
    completed = sum(1 for a in assignments if a.is_completed)
    pending   = len(assignments) - completed

    return {
        "total": len(assignments),
        "pending": pending,
        "completed": completed,
        "overdue": overdue,
        "due_today": due_today,
        "due_soon": due_soon,
        "upcoming": upcoming,
        "urgent_total": overdue + due_today + due_soon,
    }


@app.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(assignment_id: int, db: Session = Depends(get_db)):
    assignment = (
        db.query(AssignmentDB)
        .filter(AssignmentDB.id == assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment with ID {assignment_id} not found",
        )
    return assignment


@app.post("/assignments", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_assignment(
    assignment: AssignmentCreate,
    db: Session = Depends(get_db),
):
    db_assignment = AssignmentDB(
        title=assignment.title.strip(),
        subject=assignment.subject.strip(),
        deadline=assignment.deadline.strip(),
        priority=assignment.priority,
        is_completed=False,
        attachment_original_name=assignment.attachment_original_name,
        attachment_stored_name=assignment.attachment_stored_name,
        attachment_mime_type=assignment.attachment_mime_type,
        extracted_text=assignment.extracted_text,
    )
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    return {
        "message": "Assignment added successfully!",
        "assignment": AssignmentResponse.model_validate(db_assignment).model_dump(),
    }


@app.put("/assignments/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: int,
    assignment_update: AssignmentUpdate,
    db: Session = Depends(get_db),
):
    db_assignment = (
        db.query(AssignmentDB)
        .filter(AssignmentDB.id == assignment_id)
        .first()
    )
    if not db_assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment with ID {assignment_id} not found",
        )

    update_data = assignment_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and isinstance(value, str):
            value = value.strip()
        setattr(db_assignment, field, value)

    db.commit()
    db.refresh(db_assignment)
    return db_assignment


@app.patch("/assignments/{assignment_id}/toggle", response_model=AssignmentResponse)
def toggle_assignment_status(
    assignment_id: int,
    db: Session = Depends(get_db),
):
    db_assignment = (
        db.query(AssignmentDB)
        .filter(AssignmentDB.id == assignment_id)
        .first()
    )
    if not db_assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment with ID {assignment_id} not found",
        )

    db_assignment.is_completed = not db_assignment.is_completed
    db.commit()
    db.refresh(db_assignment)
    return db_assignment


@app.delete("/assignments/{assignment_id}", status_code=status.HTTP_200_OK)
def delete_assignment(assignment_id: int, db: Session = Depends(get_db)):
    db_assignment = (
        db.query(AssignmentDB)
        .filter(AssignmentDB.id == assignment_id)
        .first()
    )
    if not db_assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment with ID {assignment_id} not found",
        )

    # Also remove the stored file if present
    if db_assignment.attachment_stored_name:
        stored = UPLOADS_DIR / db_assignment.attachment_stored_name
        if stored.exists():
            stored.unlink(missing_ok=True)

    db.delete(db_assignment)
    db.commit()
    return {"message": f"Assignment with ID {assignment_id} deleted successfully"}


# ── Attachment Endpoints ────────────────────────────────────────────────────────

@app.get("/attachments/{assignment_id}")
def download_attachment(assignment_id: int, db: Session = Depends(get_db)):
    """Serve the stored file for the given assignment as a download."""
    db_assignment = (
        db.query(AssignmentDB)
        .filter(AssignmentDB.id == assignment_id)
        .first()
    )
    if not db_assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if not db_assignment.attachment_stored_name:
        raise HTTPException(status_code=404, detail="No attachment for this assignment")

    file_path = UPLOADS_DIR / db_assignment.attachment_stored_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type=db_assignment.attachment_mime_type or "application/octet-stream",
        filename=db_assignment.attachment_original_name or db_assignment.attachment_stored_name,
    )


@app.delete("/attachments/{assignment_id}", status_code=status.HTTP_200_OK)
def remove_attachment(assignment_id: int, db: Session = Depends(get_db)):
    """Remove attachment from an assignment without deleting the assignment itself."""
    db_assignment = (
        db.query(AssignmentDB)
        .filter(AssignmentDB.id == assignment_id)
        .first()
    )
    if not db_assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if not db_assignment.attachment_stored_name:
        raise HTTPException(status_code=404, detail="No attachment to remove")

    stored = UPLOADS_DIR / db_assignment.attachment_stored_name
    stored.unlink(missing_ok=True)

    db_assignment.attachment_original_name = None
    db_assignment.attachment_stored_name   = None
    db_assignment.attachment_mime_type     = None
    db_assignment.extracted_text          = None
    db.commit()
    return {"message": "Attachment removed successfully"}


# ── Document Upload (extract only) ─────────────────────────────────────────────

@app.post("/upload", response_model=dict)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF, DOCX, or image.
    - Validates type and size.
    - Extracts text and parses assignment fields.
    - Saves the file to the uploads folder with a UUID name.
    - Returns parsed fields + a `stored_name` token that POST /assignments accepts.
    """
    filename = file.filename or ""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    data = await file.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {MAX_FILE_SIZE_MB} MB.",
        )

    # Extract text
    text, error = extract_text(filename, data)
    if error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)

    parsed = parse_assignment_details(text)

    # Persist file with a unique name so it survives until the assignment is saved
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / stored_name).write_bytes(data)

    return {
        "filename": filename,
        "stored_name": stored_name,
        "mime_type": file.content_type or "application/octet-stream",
        "extracted_text": text[:3000],   # cap for the API payload
        "parsed": parsed,
    }


# ── AI Endpoints ────────────────────────────────────────────────────────────────

@app.get("/ai/status")
def get_ai_status():
    """Check whether Gemini AI is configured on the backend."""
    configured = is_ai_configured()
    return {
        "configured": configured,
        "provider": "Google Gemini",
        "model": "gemini-2.5-flash",
        "message": (
            "Gemini API is configured and ready."
            if configured
            else "GEMINI_API_KEY is not set. Add it to your .env file to enable AI features."
        ),
    }


@app.post("/ai/explain")
def explain_assignment_endpoint(request: AIExplainRequest):
    """Generate an AI concept and approach breakdown for an assignment."""
    result = ai_explain(
        title=request.title,
        subject=request.subject,
        deadline=request.deadline,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.get("error", "AI explanation failed"),
        )
    return result


@app.post("/ai/study-plan")
def study_plan_endpoint(request: AIStudyPlanRequest):
    """Generate a personalized AI day-by-day study roadmap."""
    result = ai_study_plan(
        title=request.title,
        subject=request.subject,
        deadline=request.deadline,
        daily_hours=request.daily_hours,
        student_notes=request.notes or "",
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.get("error", "AI study plan generation failed"),
        )
    return result


@app.post("/ai/chat")
def student_chat_endpoint(request: AIChatRequest):
    """University student conversational assistant."""
    msgs = [{"role": m.role, "content": m.content} for m in request.messages]
    result = student_chat_assistant(messages=msgs, context=request.context or "")
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.get("error", "AI chat failed"),
        )
    return result