import json
import os
import re
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, session, redirect, flash, Response
from agent import (
    create_empty_resume,
    process_message,
    apply_updates,
    generate_resume_summary,
    is_resume_ready,
    normalize_resume_data
)
from database import (
    create_table,
    # Users
    create_user,
    get_user_by_email,
    get_user_by_id,
    check_password,
    # Resumes
    create_resume,
    get_resumes_by_user,
    get_resume_by_id,
    update_resume,
    delete_resume,
    # Conversations
    create_conversation,
    get_conversations_by_user,
    get_conversations_by_resume,
    get_latest_conversation_by_resume,
    get_conversation_by_id,
    update_conversation_time,
    delete_conversation,
    # Messages
    save_message,
    get_messages
)

MAX_MESSAGE_LENGTH = 4000
MAX_INITIAL_TEXT_LENGTH = 5000

app = Flask(__name__)
# CHANGED: secret key can come from the environment (falls back to the old value)
app.secret_key = os.environ.get("SECRET_KEY", "my-secret-key")
# CHANGED: cookies are not sent on cross-site POSTs (basic CSRF protection)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

create_table()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render_error(message, back_url=None, status=200):
    """Shows an error inside the site layout (no raw text, no traceback)."""
    if back_url is None:
        back_url = "/dashboard" if "user_id" in session else "/"
    return render_template(
        "error.html", message=message, back_url=back_url
    ), status


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return render_error(
                "برای ادامه ابتدا وارد حساب خود شو.", "/login", 401
            )
        return function(*args, **kwargs)

    return wrapper


def load_resume_data(resume_row):
    """Reads the JSON stored in a resume row. Old/broken rows fall back to an
    empty resume that keeps the raw text as summary, so nothing crashes."""
    raw = resume_row[2]
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = None

    if not isinstance(data, dict):
        fallback = create_empty_resume()
        fallback["summary"] = raw if isinstance(raw, str) else ""
        return fallback

    return normalize_resume_data(data)


def short_text(text, limit=80):
    text = " ".join((text or "").split())
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def resume_card(resume_row):
    """Turns a get_resumes_by_user row into something the dashboard can show."""
    resume_id, raw, created_at, updated_at = resume_row
    data = load_resume_data((resume_id, None, raw))
    name = data["personal"]["name"].strip()
    return {
        "id": resume_id,
        "title": f"رزومه شماره {resume_id}",
        "subtitle": name or short_text(data["summary"]),
        "created_at": created_at,
        "updated_at": updated_at,
        "ready": is_resume_ready(data),
    }


def prune_empty_items(resume_data):
    """For the preview only: drop list items whose fields are all empty."""
    pruned = dict(resume_data)
    for section in ("education", "experience", "projects",
                    "certifications", "languages"):
        items = []
        for item in resume_data.get(section, []):
            if any(
                (any(value) if isinstance(value, list) else value)
                for value in item.values()
            ):
                items.append(item)
        pruned[section] = items
    pruned["skills"] = [s for s in resume_data.get("skills", []) if s.strip()]
    return pruned


@app.template_filter("datefmt")
def datefmt(value):
    # SQLite gives "YYYY-MM-DD HH:MM:SS" (UTC)
    return str(value)[:16] if value else ""


@app.template_filter("safe_url")
def safe_url(value):
    """Only allow http(s) links in the preview (blocks javascript: etc.)."""
    value = (value or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        return value
    if re.match(r"^[a-z][a-z0-9+.-]*:", lowered):
        return ""
    return "https://" + value


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    user = None
    if "user_id" in session:
        user = get_user_by_id(session["user_id"])
        if user is None:
            session.pop("user_id", None)
    return render_template("index.html", user=user)


@app.route("/register")
def register():
    if "user_id" in session:
        return redirect("/dashboard")
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not username or not email or not password:
        return render_error("همه فیلدها را پر کن.", "/register", 400)
    if "@" not in email:
        return render_error("یک ایمیل معتبر وارد کن.", "/register", 400)

    try:
        create_user(username, email, password)
    except sqlite3.IntegrityError:
        return render_error(
            "این نام کاربری یا ایمیل قبلاً ثبت شده است.", "/register", 400
        )
    return redirect("/login")


@app.route("/login")
def login():
    if "user_id" in session:
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_user():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email) if email else None
    # CHANGED: one message for both cases, so nobody can probe which emails exist
    if user is None or not check_password(password, user[3]):
        return render_error("ایمیل یا رمز عبور اشتباه است.", "/login", 401)

    session.clear()
    session["user_id"] = user[0]
    return redirect("/dashboard")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect("/login")

    resumes = [resume_card(row) for row in get_resumes_by_user(user_id)]
    conversations = get_conversations_by_user(user_id)
    return render_template(
        "dashboard.html",
        user=user,
        resumes=resumes,
        conversations=conversations
    )


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------

@app.route("/resume/new")
@login_required
def new_resume():
    return render_template("new-resume.html")


@app.route("/resume/new", methods=["POST"])
@login_required
def create_new_resume():
    user_id = session["user_id"]
    initial_text = request.form.get("data", "").strip()

    if not initial_text:
        return render_error(
            "اطلاعات رزومه نمی‌تواند خالی باشد.", "/resume/new", 400
        )
    if len(initial_text) > MAX_INITIAL_TEXT_LENGTH:
        return render_error("متن واردشده بیش از حد طولانی است.", "/resume/new", 400)

    resume_data = create_empty_resume()
    resume_data["summary"] = initial_text

    resume_id = create_resume(
        user_id,
        json.dumps(resume_data, ensure_ascii=False)
    )
    return redirect(f"/resume/{resume_id}")


@app.route("/resume/<int:resume_id>")
@login_required
def view_resume(resume_id):
    user_id = session["user_id"]
    resume = get_resume_by_id(resume_id, user_id)
    if resume is None:
        return render_error("رزومه پیدا نشد.", status=404)

    resume_data = load_resume_data(resume)
    return render_template(
        "resume-detail.html",
        resume_id=resume_id,
        resume_data=resume_data,
        resume_ready=is_resume_ready(resume_data),
        conversations=get_conversations_by_resume(resume_id, user_id)
    )


@app.route("/resume/<int:resume_id>/delete", methods=["POST"])
@login_required
def remove_resume(resume_id):
    if not delete_resume(resume_id, session["user_id"]):
        return render_error("رزومه پیدا نشد.", status=404)
    flash("رزومه و گفتگوهای مربوط به آن حذف شد.", "success")
    return redirect("/dashboard")


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

# CHANGED: opening a resume's chat continues the latest conversation and only
# creates one when the resume has none. (The old URL /conversation/new now
# behaves the same, so refreshing or re-clicking never piles up conversations.)
@app.route("/resume/<int:resume_id>/conversation")
@app.route("/resume/<int:resume_id>/conversation/new")
@login_required
def open_conversation(resume_id):
    user_id = session["user_id"]
    resume = get_resume_by_id(resume_id, user_id)
    if resume is None:
        return render_error("رزومه پیدا نشد.", status=404)

    latest = get_latest_conversation_by_resume(resume_id, user_id)
    if latest is not None:
        return redirect(f"/conversation/{latest[0]}")

    conversation_id = create_conversation(
        user_id, resume_id, "Resume Conversation"
    )
    return redirect(f"/conversation/{conversation_id}")


# NEW: the only place where a conversation is created on purpose (POST, so a
# refresh or a link prefetch can not create one by accident).
@app.route("/resume/<int:resume_id>/conversation/new", methods=["POST"])
@login_required
def create_new_conversation(resume_id):
    user_id = session["user_id"]
    resume = get_resume_by_id(resume_id, user_id)
    if resume is None:
        return render_error("رزومه پیدا نشد.", status=404)

    conversation_id = create_conversation(
        user_id, resume_id, "Resume Conversation"
    )
    return redirect(f"/conversation/{conversation_id}")


@app.route("/conversation/<int:conversation_id>")
@login_required
def conversation(conversation_id):
    user_id = session["user_id"]

    conversation_data = get_conversation_by_id(conversation_id, user_id)
    if conversation_data is None:
        return render_error("گفتگو پیدا نشد.", status=404)

    resume = get_resume_by_id(conversation_data[2], user_id)
    if resume is None:
        return render_error("رزومه این گفتگو پیدا نشد.", status=404)

    resume_data = load_resume_data(resume)

    return render_template(
        "conversation.html",
        conversation=conversation_data,
        messages=get_messages(conversation_id),
        resume_ready=is_resume_ready(resume_data)
    )


@app.route("/conversation/<int:conversation_id>/message", methods=["POST"])
@login_required
def send_message(conversation_id):
    user_id = session["user_id"]
    back = f"/conversation/{conversation_id}"

    conversation_data = get_conversation_by_id(conversation_id, user_id)
    if conversation_data is None:
        return render_error("گفتگو پیدا نشد.", status=404)

    content = request.form.get("content", "").strip()
    if not content:
        return redirect(back)
    if len(content) > MAX_MESSAGE_LENGTH:
        flash("پیام خیلی طولانی است. آن را کوتاه‌تر کن.", "error")
        return redirect(back)

    resume_id = conversation_data[2]
    resume = get_resume_by_id(resume_id, user_id)
    if resume is None:
        return render_error("رزومه این گفتگو پیدا نشد.", status=404)

    resume_data = load_resume_data(resume)

    # History is read BEFORE saving, because the agent receives the new
    # message separately.
    conversation_history = get_messages(conversation_id)

    # The user's message is saved first, so it is never lost if the agent fails.
    save_message(conversation_id, "user", content)
    update_conversation_time(conversation_id, user_id)

    try:
        result = process_message(content, resume_data, conversation_history)
        assistant_response = result["reply"].strip()
        if not assistant_response:
            raise ValueError("Agent returned an empty reply.")

        updates = result["updates"]
        # The summary is generated at finalize time; this keeps the user's
        # initial text (stored in "summary") from being wiped by the agent.
        updates.pop("summary", None)

        resume_data = normalize_resume_data(
            apply_updates(resume_data, updates)
        )
    except Exception:
        app.logger.exception("Agent failed for conversation %s", conversation_id)
        flash(
            "دستیار الان پاسخ نداد، ولی پیامت ذخیره شد. "
            "چند لحظه بعد دوباره پیام بده.",
            "error"
        )
        return redirect(back)

    update_resume(
        resume_id,
        user_id,
        json.dumps(resume_data, ensure_ascii=False)
    )
    save_message(conversation_id, "assistant", assistant_response)
    update_conversation_time(conversation_id, user_id)

    return redirect(back)


@app.route("/conversation/<int:conversation_id>/delete", methods=["POST"])
@login_required
def remove_conversation(conversation_id):
    user_id = session["user_id"]
    conversation_data = get_conversation_by_id(conversation_id, user_id)
    if conversation_data is None:
        return render_error("گفتگو پیدا نشد.", status=404)

    resume_id = conversation_data[2]
    delete_conversation(conversation_id, user_id)
    flash("گفتگو حذف شد.", "success")

    if request.form.get("next") == "resume":
        return redirect(f"/resume/{resume_id}")
    return redirect("/dashboard")


# ---------------------------------------------------------------------------
# Finalize + preview
# ---------------------------------------------------------------------------

@app.route("/resume/<int:resume_id>/finalize")
@login_required
def finalize_resume(resume_id):
    user_id = session["user_id"]

    resume = get_resume_by_id(resume_id, user_id)
    if resume is None:
        return render_error("رزومه پیدا نشد.", status=404)

    resume_data = load_resume_data(resume)

    if not is_resume_ready(resume_data):
        return render_error(
            "اطلاعات رزومه هنوز کافی نیست. گفتگو را ادامه بده.",
            f"/resume/{resume_id}/conversation",
            400
        )

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect("/login")

    if not resume_data["personal"]["email"]:
        resume_data["personal"]["email"] = user[2]

    try:
        summary = generate_resume_summary(resume_data)
    except Exception:
        # Details go to the terminal only, not to the user.
        app.logger.exception("Summary generation failed for resume %s", resume_id)
        return render_error(
            "ساخت خلاصه رزومه الان ممکن نشد. چند لحظه بعد دوباره تلاش کن.",
            f"/resume/{resume_id}",
            502
        )

    resume_data["summary"] = summary

    update_resume(
        resume_id,
        user_id,
        json.dumps(resume_data, ensure_ascii=False)
    )

    return render_template(
        "resume-preview.html",
        resume=prune_empty_items(resume_data),
        resume_id=resume_id
    )


# NEW: PDF download. Renders a standalone print-styled HTML page from the
# STORED resume (no LLM call) and converts it to PDF with WeasyPrint.
@app.route("/resume/<int:resume_id>/pdf")
@login_required
def download_resume_pdf(resume_id):
    user_id = session["user_id"]

    resume = get_resume_by_id(resume_id, user_id)
    if resume is None:
        return render_error("رزومه پیدا نشد.", status=404)

    resume_data = load_resume_data(resume)

    if not is_resume_ready(resume_data):
        return render_error(
            "اطلاعات رزومه هنوز کافی نیست. گفتگو را ادامه بده.",
            f"/resume/{resume_id}/conversation",
            400
        )

    try:
        from weasyprint import HTML  # imported here so the site runs without it
        html = render_template(
            "resume-pdf.html", resume=prune_empty_items(resume_data)
        )
        pdf_bytes = HTML(string=html, base_url=app.root_path).write_pdf()
    except Exception:
        app.logger.exception("PDF generation failed for resume %s", resume_id)
        return render_error(
            "ساخت فایل PDF الان ممکن نشد. چند لحظه بعد دوباره تلاش کن.",
            f"/resume/{resume_id}",
            502
        )

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="resume-{resume_id}.pdf"'
        }
    )


# ---------------------------------------------------------------------------
# Error pages (no raw text, no tracebacks)
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def handle_404(error):
    return render_error("صفحه‌ای که دنبالش بودی پیدا نشد.", status=404)


@app.errorhandler(405)
def handle_405(error):
    return render_error("این آدرس این‌طور قابل استفاده نیست.", status=405)


@app.errorhandler(500)
def handle_500(error):
    return render_error("مشکلی در سرور پیش آمد. دوباره تلاش کن.", status=500)



app.run()
