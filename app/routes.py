from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from .extensions import db
from .models import *
from .services import audit, refresh_notifications

bp = Blueprint("main", __name__)

def admin_required():
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)

@bp.before_app_request
def require_initial_admin():
    if request.endpoint in ("static", "main.setup_admin"):
        return None
    if User.query.filter_by(role="admin", active=True).count() == 0:
        return redirect(url_for("main.setup_admin"))

@bp.route("/setup-admin", methods=["GET", "POST"])
def setup_admin():
    if User.query.filter_by(role="admin", active=True).count() > 0:
        return redirect(url_for("main.login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        
        if not all((name, username, email, password)) or len(password) < 10:
            flash("Preencha todos os campos e use uma senha com pelo menos 10 caracteres.", "danger")
        else:
            user = User(name=name, username=username, email=email, role="admin", active=True)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
                login_user(user)
                return redirect(url_for("main.dashboard"))
            except IntegrityError:
                db.session.rollback()
                flash("Login ou e-mail já em uso.", "danger")
    return render_template("setup_admin.html")

@bp.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: 
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username","").strip()).first()
        if user and user.active and user.check_password(request.form.get("password","")):
            login_user(user)
            return redirect(url_for("main.dashboard"))
        flash("Usuário ou senha inválidos.", "danger")
    return render_template("login.html")

@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))

@bp.route("/")
@login_required
def dashboard():
    refresh_notifications()
    # Estatísticas para os cards do Dashboard
    stats = {
        "activities": Activity.query.filter(Activity.status != "Concluída").count(),
        "loans_today": ContingencyLoan.query.filter_by(loan_date=date.today()).count(),
        "interlibs": InterLibraryLoan.query.filter(InterLibraryLoan.return_date.is_(None)).count(),
        "notifications": Notification.query.filter_by(resolved_at=None).count() # <-- CORRIGIDO AQUI
    }
    return render_template("dashboard.html", stats=stats)

# ==========================================
# ÁREA DE ATIVIDADES
# ==========================================
@bp.route("/atividades", methods=["GET", "POST"])
@login_required
def activities():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "Normal")
        
        if not title or not description:
            flash("Informe o título e a descrição da atividade.", "danger")
        else:
            act = Activity(title=title, description=description, priority=priority, created_by_id=current_user.id)
            db.session.add(act)
            db.session.flush()
            audit(current_user, "NOVA ATIVIDADE", "Activity", act.id, title)
            db.session.commit()
            flash("Atividade registrada.", "success")
            return redirect(url_for("main.activities"))

    rows = Activity.query.order_by(Activity.status, Activity.created_at.desc()).all()
    return render_template("activities.html", rows=rows)

@bp.route("/atividades/<int:id>", methods=["GET", "POST"])
@login_required
def activity_detail(id):
    act = db.get_or_404(Activity, id)
    
    # Adicionar comentário na atividade
    if request.method == "POST" and "body" in request.form:
        body = request.form.get("body", "").strip()
        if body:
            msg = ActivityMessage(activity_id=act.id, user_id=current_user.id, body=body)
            db.session.add(msg)
            act.updated_at = datetime.utcnow()
            db.session.commit()
            return redirect(url_for("main.activity_detail", id=act.id) + "#chat")
            
    # Atualizar status da atividade
    if request.method == "POST" and "status" in request.form:
        act.status = request.form.get("status")
        db.session.commit()
        flash("Status atualizado.", "success")
        return redirect(url_for("main.activity_detail", id=act.id))

    return render_template("activity_detail.html", act=act)

# ==========================================
# ÁREA DE EMPRÉSTIMOS
# ==========================================
@bp.route("/emprestimos")
@login_required
def loans_dashboard():
    return render_template("loans_dashboard.html")

@bp.route("/emprestimos/contingencia", methods=["GET", "POST"])
@login_required
def loan_contingency():
    if request.method == "POST":
        loan = ContingencyLoan(
            user_name=request.form["user_name"],
            user_document=request.form.get("user_document"),
            user_phone=request.form.get("user_phone"),
            user_registration=request.form.get("user_registration"),
            expected_return_date=datetime.strptime(request.form["expected_return_date"], "%Y-%m-%d").date() if request.form.get("expected_return_date") else None,
            notes=request.form.get("notes"),
            created_by_id=current_user.id
        )
        db.session.add(loan)
        db.session.flush()

        book_titles = request.form.getlist("book_title[]")
        copy_codes = request.form.getlist("copy_code[]")
        item_notes = request.form.getlist("item_notes[]")

        for i in range(len(book_titles)):
            if book_titles[i].strip():
                db.session.add(ContingencyLoanItem(
                    loan_id=loan.id,
                    book_title=book_titles[i],
                    copy_code=copy_codes[i] if i < len(copy_codes) else "",
                    item_notes=item_notes[i] if i < len(item_notes) else ""
                ))

        db.session.commit()
        flash("Empréstimo de contingência registrado!", "success")
        return redirect(url_for("main.loan_contingency"))

    rows = ContingencyLoan.query.order_by(ContingencyLoan.created_at.desc()).all()
    return render_template("loan_contingency.html", rows=rows)

@bp.route("/emprestimos/interbibliotecas", methods=["GET", "POST"])
@login_required
def loan_interlibrary():
    if request.method == "POST":
        loan = InterLibraryLoan(
            requesting_library=request.form["requesting_library"],
            address=request.form.get("address"),
            phone=request.form.get("phone"),
            contact_person=request.form.get("contact_person"),
            contact_email=request.form.get("contact_email"),
            book_reference=request.form["book_reference"],
            copy_code=request.form.get("copy_code"),
            item_value=request.form.get("item_value"),
            notes=request.form.get("notes"),
            created_by_id=current_user.id
        )
        db.session.add(loan)
        db.session.commit()
        flash("Empréstimo inter-bibliotecas registrado!", "success")
        return redirect(url_for("main.loan_interlibrary"))
    
    rows = InterLibraryLoan.query.order_by(InterLibraryLoan.created_at.desc()).all()
    return render_template("loan_interlibrary.html", rows=rows)

# ==========================================
# CHAT GERAL
# ==========================================
@bp.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            db.session.add(ChatMessage(user_id=current_user.id, body=body))
            db.session.commit()
            return redirect(url_for("main.chat"))
            
    messages = ChatMessage.query.order_by(ChatMessage.created_at.asc()).limit(200).all()
    return render_template("chat.html", messages=messages)

# ==========================================
# NOTIFICAÇÕES E USUÁRIOS
# ==========================================
@bp.route("/notificacoes")
@login_required
def notifications():
    refresh_notifications()
    rows = Notification.query.order_by(Notification.resolved_at.is_(None).desc(), Notification.created_at.desc()).all()
    return render_template("notifications.html", rows=rows)

@bp.route("/notificacoes/<int:nid>/lida", methods=["POST"])
@login_required
def notification_read(nid):
    n = db.get_or_404(Notification, nid)
    if not NotificationRead.query.filter_by(notification_id=n.id, user_id=current_user.id).first():
        db.session.add(NotificationRead(notification_id=n.id, user_id=current_user.id))
    db.session.commit()
    return redirect(url_for("main.notifications"))

@bp.route("/usuarios", methods=["GET", "POST"])
@login_required
def users():
    admin_required()
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 10:
            flash("A senha precisa ter pelo menos 10 caracteres.", "danger")
        else:
            u = User(name=request.form["name"], username=request.form["username"].strip(), email=request.form["email"].strip(), role="servidor", active=True)
            u.set_password(password)
            db.session.add(u)
            try:
                db.session.commit()
                flash("Usuário criado.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("Login ou e-mail já utilizado.", "danger")
    return render_template("users.html", users=User.query.order_by(User.name).all())