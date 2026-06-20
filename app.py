from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from tempfile import NamedTemporaryFile

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from examdino_data import (
    FEATURES,
    HOME_HIGHLIGHTS,
    NAV_ITEMS,
    PAPER_LIBRARY,
    RESOURCE_COLLECTIONS,
    SITE_TAGLINE,
    SUBJECTS,
)
from examdino_utils import (
    build_quiz_items,
    build_revision_plan,
    build_study_notes,
    extract_text_from_upload,
    filter_results,
)
from igcse_lab import (
    IGCSE_SUBJECT_CODES,
    IGCSE_STRUCTURE,
    build_paper_lab_bundle,
    build_session_catalog,
    fetch_past_papers,
    get_igcse_subject_name,
    fetch_session_download_links,
    parse_pdf_text_from_links,
    text_to_pdf,
)


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = INSTANCE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PAPER_LAB_DIR = INSTANCE_DIR / "paper_lab_runs"
PAPER_LAB_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".pptx", ".json", ".log"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "examdino-dev-secret")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url or f"sqlite:///{INSTANCE_DIR / 'examdino.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access that page."
login_manager.login_message_category = "info"
token_serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    email_confirmed_at = db.Column(db.DateTime, nullable=True)

    artifacts = db.relationship(
        "StudyArtifact",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(StudyArtifact.created_at)",
    )
    folders = db.relationship(
        "SavedFolder",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="SavedFolder.name",
    )
    quiz_history = db.relationship(
        "QuizHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(QuizHistory.created_at)",
    )
    paper_history = db.relationship(
        "PaperHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(PaperHistory.created_at)",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def email_confirmed(self) -> bool:
        return self.email_confirmed_at is not None


class SavedFolder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="folders")
    quiz_history = db.relationship("QuizHistory", back_populates="folder")
    paper_history = db.relationship("PaperHistory", back_populates="folder")


class QuizHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    folder_id = db.Column(db.Integer, db.ForeignKey("saved_folder.id"), nullable=True, index=True)
    subject_slug = db.Column(db.String(80), nullable=False, index=True)
    prompt_text = db.Column(db.Text, nullable=False, default="")
    items_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", back_populates="quiz_history")
    folder = db.relationship("SavedFolder", back_populates="quiz_history")

    @property
    def items(self) -> list[dict[str, object]]:
        try:
            return json.loads(self.items_json)
        except json.JSONDecodeError:
            return []


class PaperHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    folder_id = db.Column(db.Integer, db.ForeignKey("saved_folder.id"), nullable=True, index=True)
    subject_name = db.Column(db.String(80), nullable=False, index=True)
    subject_code = db.Column(db.String(20), nullable=False, index=True)
    year_range = db.Column(db.String(40), nullable=True)
    source_mode = db.Column(db.String(20), nullable=False)
    selected_session_url = db.Column(db.Text, nullable=True)
    summary_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", back_populates="paper_history")
    folder = db.relationship("SavedFolder", back_populates="paper_history")

    @property
    def summary(self) -> dict[str, object]:
        try:
            return json.loads(self.summary_json)
        except json.JSONDecodeError:
            return {}


class StudyArtifact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(80), nullable=True, index=True)
    payload_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", back_populates="artifacts")

    @property
    def payload(self) -> dict[str, object]:
        try:
            return json.loads(self.payload_json)
        except json.JSONDecodeError:
            return {}


login_manager.init_app(app)
db.init_app(app)


@login_manager.user_loader
def load_user(user_id: str):
    if not user_id:
        return None
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


with app.app_context():
    db.create_all()


def all_courses():
    return [SUBJECTS[key] for key in SUBJECTS]


def get_course(slug: str):
    return SUBJECTS.get(slug)


def section_cards():
    return [
        {
            "title": "Courses",
            "slug": "courses",
            "summary": "Study the main IGCSE subjects through chapter maps, checkpoints, and paper lanes.",
        },
        {
            "title": "Notes",
            "slug": "notes",
            "summary": "Paste text or upload slides and get revision notes, flashcards, and key terms.",
        },
        {
            "title": "Past Papers",
            "slug": "papers",
            "summary": "Use a searchable library of practice lanes and official Cambridge entry points.",
        },
        {
            "title": "Quizzes",
            "slug": "quizzes",
            "summary": "Generate targeted quizzes from subject topics or uploaded material.",
        },
        {
            "title": "Upload Studio",
            "slug": "upload_page",
            "summary": "Drop in PDFs, PPTX files, or text files and build a study pack automatically.",
        },
        {
            "title": "Planner",
            "slug": "planner",
            "summary": "Create a weekly revision schedule with weak-topic radar and timed sessions.",
        },
    ]


def make_search_index():
    items = []
    for course in all_courses():
        items.append(
            {
                "kind": "Course",
                "title": course.name,
                "slug": course.slug,
                "description": course.overview,
                "link": url_for("course_detail", slug=course.slug),
            }
        )
    for feature in FEATURES:
        items.append(
            {
                "kind": "Feature",
                "title": feature["title"],
                "slug": feature["slug"],
                "description": feature["summary"],
                "link": url_for(feature["slug"] if feature["slug"] != "upload" else "upload_page"),
            }
        )
    for item in PAPER_LIBRARY:
        course = SUBJECTS[item["subject"]]
        items.append(
            {
                "kind": "Paper",
                "title": item["title"],
                "slug": item["subject"],
                "description": item["description"],
                "link": url_for("course_detail", slug=course.slug),
            }
        )
    return items


def _parse_positive_int(raw_value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _parse_optional_int(raw_value: str | None) -> int | None:
    try:
        if raw_value in {None, ""}:
            return None
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _normalize_identifier(value: str) -> str:
    return value.strip().lower()


def _generate_token(user_id: int, purpose: str) -> str:
    return token_serializer.dumps({"user_id": user_id, "purpose": purpose})


def _decode_token(token: str, purpose: str, max_age: int) -> int | None:
    try:
        data = token_serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or data.get("purpose") != purpose:
        return None
    try:
        return int(data["user_id"])
    except (TypeError, ValueError, KeyError):
        return None


def _mail_settings() -> dict[str, object]:
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": _parse_positive_int(os.environ.get("SMTP_PORT", "587"), 587, 1, 65535),
        "username": os.environ.get("SMTP_USERNAME", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no"},
        "from_email": os.environ.get("MAIL_FROM")
        or os.environ.get("SMTP_USERNAME")
        or "no-reply@examdino.local",
    }


def _build_email_message(recipient: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    settings = _mail_settings()
    message["Subject"] = subject
    message["From"] = str(settings["from_email"])
    message["To"] = recipient
    message.set_content(body)
    return message


def deliver_email(recipient: str, subject: str, body: str) -> bool:
    settings = _mail_settings()
    host = str(settings["host"])
    if not host:
        app.logger.info("DEV EMAIL to %s | %s\n%s", recipient, subject, body)
        return False

    message = _build_email_message(recipient, subject, body)
    port = int(settings["port"])
    username = str(settings["username"])
    password = str(settings["password"])
    use_tls = bool(settings["use_tls"])

    with smtplib.SMTP(host, port, timeout=20) as client:
        if use_tls:
            client.starttls()
        if username and password:
            client.login(username, password)
        client.send_message(message)
    return True


def build_confirmation_email(user: User) -> tuple[str, str]:
    token = _generate_token(user.id, "email-confirm")
    confirm_url = url_for("confirm_email", token=token, _external=True)
    subject = "Confirm your ExamDino email"
    body = (
        f"Hi {user.username},\n\n"
        "Confirm your ExamDino account by opening this link:\n"
        f"{confirm_url}\n\n"
        "If you did not create this account, you can ignore this message."
    )
    return subject, body


def build_password_reset_email(user: User) -> tuple[str, str, str]:
    token = _generate_token(user.id, "password-reset")
    reset_url = url_for("reset_password", token=token, _external=True)
    subject = "Reset your ExamDino password"
    body = (
        f"Hi {user.username},\n\n"
        "Reset your ExamDino password here:\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this message."
    )
    return token, subject, body


def create_default_folders(user: User) -> list[SavedFolder]:
    defaults = [
        ("quiz", "Quiz History"),
        ("paper", "Paper Sessions"),
        ("general", "General"),
    ]
    created: list[SavedFolder] = []
    for kind, name in defaults:
        folder = SavedFolder.query.filter_by(user_id=user.id, kind=kind, name=name).first()
        if not folder:
            folder = SavedFolder(user_id=user.id, kind=kind, name=name)
            db.session.add(folder)
            created.append(folder)
    if created:
        db.session.commit()
    return SavedFolder.query.filter_by(user_id=user.id).order_by(SavedFolder.kind, SavedFolder.name).all()


def get_user_folders(user: User, kind: str | None = None) -> list[SavedFolder]:
    query = SavedFolder.query.filter_by(user_id=user.id)
    if kind:
        query = query.filter_by(kind=kind)
    return query.order_by(SavedFolder.name.asc()).all()


def get_or_create_default_folder(user: User, kind: str) -> SavedFolder | None:
    folder = SavedFolder.query.filter_by(user_id=user.id, kind=kind).order_by(SavedFolder.created_at.asc()).first()
    if folder:
        return folder
    name_map = {"quiz": "Quiz History", "paper": "Paper Sessions", "general": "General"}
    folder = SavedFolder(user_id=user.id, kind=kind, name=name_map.get(kind, "General"))
    db.session.add(folder)
    db.session.commit()
    return folder


def save_quiz_history(user: User, subject_slug: str, prompt_text: str, items: list[dict[str, object]], folder_id: int | None = None) -> QuizHistory:
    folder = None
    if folder_id:
        folder = SavedFolder.query.filter_by(id=folder_id, user_id=user.id, kind="quiz").first()
    if folder is None:
        folder = get_or_create_default_folder(user, "quiz")
    quiz = QuizHistory(
        user_id=user.id,
        folder_id=folder.id if folder else None,
        subject_slug=subject_slug,
        prompt_text=prompt_text,
        items_json=json.dumps(items, ensure_ascii=True),
    )
    db.session.add(quiz)
    db.session.commit()
    return quiz


def save_paper_history(
    user: User,
    subject_name: str,
    subject_code: str,
    year_range: str,
    source_mode: str,
    selected_session_url: str,
    fetch_links: list[str],
    bundle: dict[str, object],
    folder_id: int | None = None,
) -> PaperHistory:
    folder = None
    if folder_id:
        folder = SavedFolder.query.filter_by(id=folder_id, user_id=user.id, kind="paper").first()
    if folder is None:
        folder = get_or_create_default_folder(user, "paper")
    summary = {
        "run_id": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        "source_mode": source_mode,
        "selected_session_url": selected_session_url,
        "fetch_links": fetch_links[:20],
        "structure": IGCSE_STRUCTURE.get(subject_name, []),
        "question_count": len(bundle.get("questions", [])),
        "mcq_count": len(bundle.get("mcq_questions", [])),
        "text_count": len(bundle.get("text_questions", [])),
        "sample_text": bundle.get("sample_text", ""),
    }
    session = PaperHistory(
        user_id=user.id,
        folder_id=folder.id if folder else None,
        subject_name=subject_name,
        subject_code=subject_code,
        year_range=year_range,
        source_mode=source_mode,
        selected_session_url=selected_session_url or None,
        summary_json=json.dumps(summary, ensure_ascii=True),
    )
    db.session.add(session)
    db.session.commit()
    return session


def save_study_artifact(user: User, kind: str, title: str, subject: str | None, payload: dict[str, object]) -> StudyArtifact:
    artifact = StudyArtifact(
        user_id=user.id,
        kind=kind,
        title=title,
        subject=subject,
        payload_json=json.dumps(payload, ensure_ascii=True),
    )
    db.session.add(artifact)
    db.session.commit()
    return artifact


def load_study_artifacts(user: User, limit: int = 20) -> list[StudyArtifact]:
    return (
        StudyArtifact.query.filter_by(user_id=user.id)
        .order_by(StudyArtifact.created_at.desc())
        .limit(limit)
        .all()
    )


def _auth_redirect_target(default: str = "dashboard") -> str:
    next_target = request.args.get("next") or request.form.get("next")
    if next_target and next_target.startswith("/"):
        return next_target
    return url_for(default)


def _email_notice_context(title: str, message: str, action_url: str | None = None, action_label: str | None = None):
    return {
        "title": title,
        "message": message,
        "action_url": action_url,
        "action_label": action_label,
    }


@app.context_processor
def inject_globals():
    return {
        "nav_items": NAV_ITEMS,
        "current_year": datetime.utcnow().year,
        "site_tagline": SITE_TAGLINE,
    }


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    errors: list[str] = []
    username = ""
    email = ""
    notice_context = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(username) < 3:
            errors.append("Username must be at least 3 characters long.")
        if "@" not in email:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if not errors:
            existing_username = User.query.filter(func.lower(User.username) == _normalize_identifier(username)).first()
            existing_email = User.query.filter(func.lower(User.email) == _normalize_identifier(email)).first()
            if existing_username:
                errors.append("That username is already taken.")
            if existing_email:
                errors.append("That email is already registered.")

        if not errors:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            create_default_folders(user)
            confirm_subject, confirm_body = build_confirmation_email(user)
            sent = deliver_email(user.email, confirm_subject, confirm_body)
            confirm_url = url_for("confirm_email", token=_generate_token(user.id, "email-confirm"), _external=True)
            if sent:
                notice_context = _email_notice_context(
                    "Check your inbox",
                    "We sent a confirmation link to your email address. Please confirm it before logging in.",
                )
            else:
                notice_context = _email_notice_context(
                    "Development confirmation",
                    "Email delivery is not configured in this environment, so use the local confirmation link below.",
                    action_url=confirm_url,
                    action_label="Confirm email",
                )
            return render_template("email_notice.html", page_title="Confirm email", active_page="register", **notice_context)

    return render_template(
        "register.html",
        page_title="Create account",
        active_page="register",
        errors=errors,
        username=username,
        email=email,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    errors: list[str] = []
    identifier = ""

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        user = (
            User.query.filter(func.lower(User.username) == _normalize_identifier(identifier)).first()
            or User.query.filter(func.lower(User.email) == _normalize_identifier(identifier)).first()
        )
        if not user or not user.check_password(password):
            errors.append("We couldn't match those credentials.")
        elif not user.email_confirmed:
            flash("Please confirm your email before logging in.", "warning")
            return redirect(url_for("confirm_email_request", email=user.email))
        else:
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(_auth_redirect_target())

    return render_template(
        "login.html",
        page_title="Log in",
        active_page="login",
        errors=errors,
        identifier=identifier,
    )


@app.route("/confirm-email", methods=["GET", "POST"])
def confirm_email_request():
    email = request.args.get("email", "").strip()
    notice_context = None
    errors: list[str] = []

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user = User.query.filter(func.lower(User.email) == _normalize_identifier(email)).first()
        if not user:
            errors.append("If that email exists, a confirmation link will be sent.")
        elif user.email_confirmed:
            flash("That email is already confirmed. You can log in now.", "success")
            return redirect(url_for("login"))
        else:
            confirm_subject, confirm_body = build_confirmation_email(user)
            sent = deliver_email(user.email, confirm_subject, confirm_body)
            confirm_url = url_for("confirm_email", token=_generate_token(user.id, "email-confirm"), _external=True)
            if sent:
                notice_context = _email_notice_context(
                    "Confirmation email sent",
                    "Check your inbox for the latest verification link.",
                )
            else:
                notice_context = _email_notice_context(
                    "Development confirmation",
                    "Email delivery is not configured here, so use the local confirmation link below.",
                    action_url=confirm_url,
                    action_label="Confirm email",
                )
            return render_template("email_notice.html", page_title="Confirm email", active_page="login", **notice_context)

    return render_template(
        "confirm_email_request.html",
        page_title="Confirm email",
        active_page="login",
        email=email,
        errors=errors,
    )


@app.route("/confirm-email/<token>")
def confirm_email(token: str):
    user_id = _decode_token(token, "email-confirm", max_age=60 * 60 * 24 * 3)
    if user_id is None:
        flash("That confirmation link is invalid or expired.", "error")
        return redirect(url_for("confirm_email_request"))

    user = db.session.get(User, user_id)
    if not user:
        flash("That confirmation link no longer matches an account.", "error")
        return redirect(url_for("confirm_email_request"))

    user.email_confirmed_at = datetime.utcnow()
    db.session.commit()
    flash("Email confirmed. You can log in now.", "success")
    return redirect(url_for("login"))


@app.route("/logout", methods=["POST", "GET"])
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    artifacts = load_study_artifacts(current_user, limit=40)
    folders = get_user_folders(current_user)
    quiz_history = current_user.quiz_history[:20]
    paper_history = current_user.paper_history[:20]
    return render_template(
        "dashboard.html",
        page_title="Dashboard",
        active_page="dashboard",
        artifacts=artifacts,
        folders=folders,
        quiz_history=quiz_history,
        paper_history=paper_history,
    )


@app.route("/folders", methods=["POST"])
@login_required
def create_folder():
    name = request.form.get("name", "").strip()
    kind = request.form.get("kind", "general").strip().lower()
    if len(name) < 2:
        flash("Folder names need at least 2 characters.", "error")
        return redirect(url_for("dashboard"))
    if kind not in {"quiz", "paper", "general"}:
        kind = "general"
    existing = SavedFolder.query.filter_by(user_id=current_user.id, kind=kind, name=name).first()
    if existing:
        flash("That folder already exists.", "info")
        return redirect(url_for("dashboard"))
    folder = SavedFolder(user_id=current_user.id, kind=kind, name=name)
    db.session.add(folder)
    db.session.commit()
    flash("Folder created.", "success")
    return redirect(url_for("dashboard"))


@app.route("/dashboard/artifacts/<int:artifact_id>/delete", methods=["POST"])
@login_required
def delete_artifact(artifact_id: int):
    artifact = StudyArtifact.query.filter_by(id=artifact_id, user_id=current_user.id).first_or_404()
    db.session.delete(artifact)
    db.session.commit()
    flash("Saved item removed.", "success")
    return redirect(url_for("dashboard"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    notice_context = None
    errors: list[str] = []
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user = User.query.filter(func.lower(User.email) == _normalize_identifier(email)).first()
        if not user:
            errors.append("If that account exists, we will send a reset link.")
        else:
            token, subject, body = build_password_reset_email(user)
            sent = deliver_email(user.email, subject, body)
            reset_url = url_for("reset_password", token=token, _external=True)
            if sent:
                notice_context = _email_notice_context(
                    "Reset link sent",
                    "Check your inbox for a password reset link.",
                )
            else:
                notice_context = _email_notice_context(
                    "Development reset link",
                    "Email delivery is not configured here, so use the local reset link below.",
                    action_url=reset_url,
                    action_label="Reset password",
                )
            return render_template("email_notice.html", page_title="Password reset", active_page="login", **notice_context)

    return render_template(
        "request_reset.html",
        page_title="Reset password",
        active_page="login",
        email=email,
        errors=errors,
    )


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    user_id = _decode_token(token, "password-reset", max_age=60 * 60 * 2)
    if user_id is None:
        flash("That reset link is invalid or expired.", "error")
        return redirect(url_for("forgot_password"))

    user = db.session.get(User, user_id)
    if not user:
        flash("That reset link no longer matches an account.", "error")
        return redirect(url_for("forgot_password"))

    errors: list[str] = []
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if not errors:
            user.set_password(password)
            db.session.commit()
            flash("Password updated. You can log in now.", "success")
            return redirect(url_for("login"))

    return render_template(
        "reset_password.html",
        page_title="Reset password",
        active_page="login",
        errors=errors,
        token=token,
    )


@app.route("/")
def home():
    spotlight = all_courses()[:3]
    return render_template(
        "index.html",
        page_title="ExamDino",
        active_page="home",
        features=FEATURES,
        highlights=HOME_HIGHLIGHTS,
        spotlight=spotlight,
        collections=RESOURCE_COLLECTIONS,
    )


@app.route("/about")
def about():
    return render_template(
        "about.html",
        page_title="About ExamDino",
        active_page="about",
        scraped_sources=[course.source_url for course in all_courses()],
    )


@app.route("/courses")
def courses():
    query = request.args.get("q", "").strip()
    courses_list = all_courses()
    if query:
        courses_list = [
            course
            for course in courses_list
            if query.lower() in f"{course.name} {course.overview} {' '.join(course.focus)}".lower()
        ]
    return render_template(
        "courses.html",
        page_title="Course Maps",
        active_page="courses",
        courses=courses_list,
        all_courses=all_courses(),
        query=query,
    )


@app.route("/courses/<slug>")
def course_detail(slug: str):
    course = get_course(slug)
    if not course:
        abort(404)

    related_papers = [paper for paper in PAPER_LIBRARY if paper["subject"] == slug]
    return render_template(
        "course_detail.html",
        page_title=course.name,
        active_page="courses",
        course=course,
        related_papers=related_papers,
        revision_plan=build_revision_plan(course.name, weak_topics=list(course.focus)),
        quiz_items=build_quiz_items(course.name, list(course.focus)),
    )


@app.route("/notes", methods=["GET", "POST"])
def notes():
    source_text = ""
    subject_slug = request.form.get("subject", "maths")
    generated = None
    if request.method == "POST":
        source_text = request.form.get("source_text", "").strip()
        subject_slug = request.form.get("subject", subject_slug)
        course = get_course(subject_slug) or all_courses()[0]
        generated = build_study_notes(source_text, course.name)
        if current_user.is_authenticated and generated:
            save_study_artifact(current_user, "notes", f"{course.name} notes", course.slug, generated)
    return render_template(
        "notes.html",
        page_title="Notes Studio",
        active_page="notes",
        courses=all_courses(),
        generated=generated,
        source_text=source_text,
        selected_subject=subject_slug,
    )


@app.route("/papers")
def papers():
    subject_filter = request.args.get("subject", "").strip().lower()
    difficulty_filter = request.args.get("difficulty", "").strip().lower()
    query = request.args.get("q", "").strip()

    results = PAPER_LIBRARY[:]
    if subject_filter:
        results = [item for item in results if item["subject"] == subject_filter]
    if difficulty_filter:
        results = [item for item in results if difficulty_filter in item["difficulty"].lower()]
    if query:
        results = filter_results(query, results)

    prepared = []
    for item in results:
        course = SUBJECTS[item["subject"]]
        prepared.append(
            {
                **item,
                "course_name": course.name,
                "course_url": url_for("course_detail", slug=item["subject"]),
            }
        )

    return render_template(
        "papers.html",
        page_title="Past Papers",
        active_page="papers",
        papers=prepared,
        subjects=all_courses(),
        subject_filter=subject_filter,
        difficulty_filter=difficulty_filter,
        query=query,
    )


@app.route("/quizzes", methods=["GET", "POST"])
def quizzes():
    selected_subject = request.form.get("subject", "maths")
    prompt_text = request.form.get("prompt_text", "").strip()
    course = get_course(selected_subject) or all_courses()[0]
    selected_folder_id = _parse_optional_int(request.form.get("folder_id"))
    quiz_folders = get_user_folders(current_user, "quiz") if current_user.is_authenticated else []
    quiz_items = []

    if request.method == "POST":
        quiz_items = build_quiz_items(course.name, list(course.focus), prompt_text)
        if current_user.is_authenticated:
            save_quiz_history(current_user, course.slug, prompt_text, quiz_items, folder_id=selected_folder_id)
    else:
        quiz_items = build_quiz_items(course.name, list(course.focus), course.overview)

    return render_template(
        "quizzes.html",
        page_title="Quiz Lab",
        active_page="quizzes",
        courses=all_courses(),
        selected_subject=selected_subject,
        prompt_text=prompt_text,
        quiz_items=quiz_items,
        quiz_folders=quiz_folders,
        selected_folder_id=selected_folder_id,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    result = None
    selected_subject = request.form.get("subject", "maths")
    pasted_text = request.form.get("pasted_text", "").strip()
    uploaded_name = ""

    if request.method == "POST":
        course = get_course(selected_subject) or all_courses()[0]
        upload = request.files.get("file")
        raw_text = pasted_text

        if upload and upload.filename:
            filename = secure_filename(upload.filename)
            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
                result = {
                    "error": "That file type is not supported yet.",
                }
            else:
                with NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as temp_file:
                    upload.save(temp_file.name)
                    uploaded_name = filename
                    try:
                        extracted = extract_text_from_upload(temp_file.name)
                        raw_text = raw_text or extracted
                    finally:
                        try:
                            os.unlink(temp_file.name)
                        except FileNotFoundError:
                            pass
        if raw_text and result is None:
            result = build_study_notes(raw_text, course.name)
            result["quiz"] = build_quiz_items(course.name, list(course.focus), raw_text)
            result["next_steps"] = build_revision_plan(course.name, weak_topics=result["terms"][:4] if result["terms"] else list(course.focus))
            if current_user.is_authenticated:
                save_study_artifact(current_user, "upload_pack", f"{course.name} study pack", course.slug, result)

    return render_template(
        "upload.html",
        page_title="Slide Studio",
        active_page="upload_page",
        courses=all_courses(),
        selected_subject=selected_subject,
        pasted_text=pasted_text,
        result=result,
        uploaded_name=uploaded_name,
    )


@app.route("/planner", methods=["GET", "POST"])
def planner():
    selected_subject = request.form.get("subject", "maths")
    study_days = request.form.get("study_days", "7")
    exam_date_str = request.form.get("exam_date", "")
    weak_topics_input = request.form.get("weak_topics", "")
    course = get_course(selected_subject) or all_courses()[0]
    try:
        planned_days = max(3, min(int(study_days or 7), 21))
    except ValueError:
        planned_days = 7
    plan = build_revision_plan(course.name, days=planned_days, weak_topics=[])

    if request.method == "POST":
        weak_topics = [part.strip() for part in weak_topics_input.split(",") if part.strip()]
        try:
            planned_days = max(3, min(int(study_days or 7), 21))
        except ValueError:
            planned_days = 7
        plan = build_revision_plan(course.name, days=planned_days, weak_topics=weak_topics)
        if exam_date_str:
            try:
                exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
                today = datetime.utcnow().date()
                span = max((exam_date - today).days, 1)
                plan = build_revision_plan(course.name, days=min(span, 21), weak_topics=weak_topics or list(course.focus))
            except ValueError:
                pass
        if current_user.is_authenticated:
            save_study_artifact(
                current_user,
                "planner",
                f"{course.name} revision plan",
                course.slug,
                {
                    "exam_date": exam_date_str,
                    "study_days": planned_days,
                    "weak_topics": weak_topics_input,
                    "plan": plan,
                },
            )

    return render_template(
        "planner.html",
        page_title="Revision Planner",
        active_page="planner",
        courses=all_courses(),
        selected_subject=selected_subject,
        exam_date=exam_date_str,
        study_days=study_days,
        weak_topics_input=weak_topics_input,
        plan=plan,
        course=course,
    )


@app.route("/paper-lab", methods=["GET", "POST"])
def paper_lab():
    selected_subject_name = request.form.get("subject_name", "Biology")
    selected_subject_code = request.form.get("subject_code", IGCSE_SUBJECT_CODES.get(selected_subject_name, "0610"))
    year_range = request.form.get("year_range", "")
    selected_session_url = request.form.get("session_url", "")
    max_pdfs = _parse_positive_int(request.form.get("max_pdfs", "8"), 8, 1, 20)
    max_questions = _parse_positive_int(request.form.get("max_questions", "1000"), 1000, 100, 5000)
    use_web = request.form.get("use_web") == "on"
    pasted_text = request.form.get("pasted_text", "").strip()
    uploaded_name = ""
    selected_folder_id = _parse_optional_int(request.form.get("folder_id"))
    fetch_links: list[str] = []
    browser_sessions: list[dict[str, object]] = []
    bundle = None
    run_id = None
    artifact_links: dict[str, str] = {}
    source_mode = "paste"
    paper_folders = get_user_folders(current_user, "paper") if current_user.is_authenticated else []

    if request.method == "POST":
        subject_name = get_igcse_subject_name(selected_subject_code)
        if subject_name == "Code not found":
            subject_name = selected_subject_name
        selected_subject_name = subject_name

        raw_text = pasted_text
        upload = request.files.get("file")
        if upload and upload.filename:
            filename = secure_filename(upload.filename)
            suffix = Path(filename).suffix.lower()
            if suffix in ALLOWED_UPLOAD_EXTENSIONS:
                with NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as temp_file:
                    upload.save(temp_file.name)
                    uploaded_name = filename
                    try:
                        raw_text = raw_text or extract_text_from_upload(temp_file.name)
                    finally:
                        try:
                            os.unlink(temp_file.name)
                        except FileNotFoundError:
                            pass
            else:
                raw_text = ""

        if use_web:
            source_mode = "web"
            browser_sessions = build_session_catalog(selected_subject_code, year_range or None, limit=30)
            if selected_session_url:
                fetch_links = fetch_session_download_links(selected_session_url)
            elif browser_sessions:
                first_session = browser_sessions[0]
                fetch_links = fetch_session_download_links(str(first_session["page_url"]))

            if fetch_links:
                web_text = parse_pdf_text_from_links(fetch_links, max_pdfs=max_pdfs)
                if web_text.strip():
                    raw_text = web_text

        if raw_text:
            bundle = build_paper_lab_bundle(selected_subject_name, raw_text, max_questions=max_questions)
            run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            run_dir = PAPER_LAB_DIR / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            files = {
                "extracted_text.txt": bundle["raw_text"],
                "questions.json": json.dumps(bundle["questions"], indent=2, ensure_ascii=True),
                "mcq_questions.json": json.dumps(bundle["mcq_questions"], indent=2, ensure_ascii=True),
                "text_questions.json": json.dumps(bundle["text_questions"], indent=2, ensure_ascii=True),
                "generated_paper.json": json.dumps(bundle["paper"], indent=2, ensure_ascii=True),
                "sample_paper.txt": bundle["sample_text"],
            }
            for name, contents in files.items():
                (run_dir / name).write_text(contents, encoding="utf-8")
            if bundle["sample_text"]:
                text_to_pdf(bundle["sample_text"], str(run_dir / "generated_paper.pdf"))
                files["generated_paper.pdf"] = ""
            artifact_links = {
                name: url_for("paper_lab_artifact", run_id=run_id, filename=name)
                for name in files
            }
            if current_user.is_authenticated:
                save_paper_history(
                    current_user,
                    selected_subject_name,
                    selected_subject_code,
                    year_range,
                    source_mode,
                    selected_session_url,
                    fetch_links,
                    bundle,
                    folder_id=selected_folder_id,
                )

    return render_template(
        "paper_lab.html",
        page_title="IGCSE Paper Lab",
        active_page="paper_lab",
        subject_names=sorted(IGCSE_SUBJECT_CODES.keys()),
        subject_codes=IGCSE_SUBJECT_CODES,
        selected_subject_name=selected_subject_name,
        selected_subject_code=selected_subject_code,
        year_range=year_range,
        max_pdfs=max_pdfs,
        max_questions=max_questions,
        use_web=use_web,
        pasted_text=pasted_text,
        uploaded_name=uploaded_name,
        selected_session_url=selected_session_url,
        fetch_links=fetch_links,
        browser_sessions=browser_sessions,
        bundle=bundle,
        run_id=run_id,
        artifact_links=artifact_links,
        source_mode=source_mode,
        structure=IGCSE_STRUCTURE.get(selected_subject_name, []),
        paper_folders=paper_folders,
        selected_folder_id=selected_folder_id,
    )


@app.route("/paper-lab/artifacts/<run_id>/<path:filename>")
def paper_lab_artifact(run_id: str, filename: str):
    run_dir = (PAPER_LAB_DIR / run_id).resolve()
    file_path = (run_dir / filename).resolve()
    try:
        if not file_path.exists() or not file_path.is_relative_to(run_dir):
            abort(404)
    except AttributeError:
        if not str(file_path).startswith(str(run_dir)) or not file_path.exists():
            abort(404)
    return send_file(file_path, as_attachment=True)


@app.route("/library")
def library():
    return render_template(
        "library.html",
        page_title="Resource Library",
        active_page="library",
        collections=RESOURCE_COLLECTIONS,
        courses=all_courses(),
        resources=[
            {"title": "Official Cambridge subject pages", "description": "Use the live syllabus pages for authoritative overviews and resource links."},
            {"title": "Generated notes", "description": "Combine upload output, flashcards, and summary bullets into a reusable study pack."},
            {"title": "Exam pack templates", "description": "Mix timed practice, recall drills, and mark-scheme review sessions."},
        ],
    )


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    search_index = make_search_index()
    results = filter_results(query, search_index) if query else search_index
    return render_template(
        "search.html",
        page_title="Search ExamDino",
        active_page="search",
        query=query,
        results=results,
    )


@app.route("/api/course/<slug>")
def course_api(slug: str):
    course = get_course(slug)
    if not course:
        return jsonify({"error": "not found"}), 404
    return jsonify(
        {
            "slug": course.slug,
            "name": course.name,
            "code": course.code,
            "board": course.board,
            "level": course.level,
            "overview": course.overview,
            "focus": course.focus,
            "chapters": course.chapters,
            "paper_lanes": course.paper_lanes,
            "source_url": course.source_url,
            "resource_url": course.resource_url,
        }
    )


@app.route("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Sitemap: " + url_for("sitemap_xml", _external=True),
    ]
    return app.response_class("\n".join(lines) + "\n", mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    routes = ["home", "about", "courses", "notes", "papers", "quizzes", "upload_page", "planner", "library", "search"]
    urls = [url_for(route, _external=True) for route in routes]
    urls.extend([url_for("course_detail", slug=course.slug, _external=True) for course in all_courses()])

    items = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
    return app.response_class(xml, mimetype="application/xml")


@app.errorhandler(404)
def page_not_found(_error):
    return render_template(
        "error_404.html",
        page_title="Page not found",
        active_page="",
    ), 404


if __name__ == "__main__":
    app.run(debug=True)
