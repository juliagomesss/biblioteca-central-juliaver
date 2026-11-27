from datetime import date, datetime
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from openpyxl.styles import Font
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
    stats = {
        "activities": Activity.query.filter(Activity.status != "Concluída").count(),
        "loans_today": ContingencyLoan.query.filter_by(loan_date=date.today()).count(),
        "interlibs": InterLibraryLoan.query.filter_by(status="Pendente").count(),
        "notifications": Notification.query.filter_by(resolved_at=None).count()
    }
    return render_template("dashboard.html", stats=stats)

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
            db.session.add(act); db.session.flush()
            audit(current_user, "NOVA ATIVIDADE", "Activity", act.id, title)
            db.session.commit(); flash("Atividade registrada.", "success")
            return redirect(url_for("main.activities"))
    rows = Activity.query.order_by(Activity.status, Activity.created_at.desc()).all()
    return render_template("activities.html", rows=rows)

@bp.route("/atividades/<int:id>", methods=["GET", "POST"])
@login_required
def activity_detail(id):
    act = db.get_or_404(Activity, id)
    if request.method == "POST" and "body" in request.form:
        body = request.form.get("body", "").strip()
        if body:
            db.session.add(ActivityMessage(activity_id=act.id, user_id=current_user.id, body=body))
            act.updated_at = datetime.utcnow(); db.session.commit()
            return redirect(url_for("main.activity_detail", id=act.id) + "#chat")
    if request.method == "POST" and "status" in request.form:
        act.status = request.form.get("status"); db.session.commit()
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
        # Captura a data enviada ou usa hoje como padrão
        date_str = request.form.get("loan_date")
        dt_loan = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        
        loan = ContingencyLoan(
            loan_date=dt_loan,
            user_name=request.form["user_name"], user_document=request.form.get("user_document"),
            user_phone=request.form.get("user_phone"), user_registration=request.form.get("user_registration"),
            expected_return_date=datetime.strptime(request.form["expected_return_date"], "%Y-%m-%d").date() if request.form.get("expected_return_date") else None,
            notes=request.form.get("notes"), created_by_id=current_user.id, status="Emprestado"
        )
        db.session.add(loan); db.session.flush()
        book_titles = request.form.getlist("book_title[]"); copy_codes = request.form.getlist("copy_code[]"); item_notes = request.form.getlist("item_notes[]")
        for i in range(len(book_titles)):
            if book_titles[i].strip():
                db.session.add(ContingencyLoanItem(loan_id=loan.id, book_title=book_titles[i], copy_code=copy_codes[i] if i < len(copy_codes) else "", item_notes=item_notes[i] if i < len(item_notes) else ""))
        db.session.commit(); flash("Empréstimo registrado!", "success")
        return redirect(url_for("main.loan_contingency"))

    query = ContingencyLoan.query
    term = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    
    if term:
        like = f"%{term}%"
        query = query.filter(or_(ContingencyLoan.user_name.ilike(like), ContingencyLoan.user_registration.ilike(like)))
    if status_filter:
        query = query.filter(ContingencyLoan.status == status_filter)
        
    rows = query.order_by(ContingencyLoan.loan_date.desc(), ContingencyLoan.id.desc()).all()
    return render_template("loan_contingency.html", rows=rows, term=term, status_filter=status_filter, today=date.today())

@bp.route("/emprestimos/contingencia/<int:id>/devolver", methods=["POST"])
@login_required
def loan_contingency_return(id):
    loan = db.get_or_404(ContingencyLoan, id)
    if loan.status != "Devolvido":
        loan.returned_at = datetime.utcnow()
        loan.status = "Devolvido"
        db.session.commit()
        flash("Devolução registrada com sucesso!", "success")
    return redirect(url_for("main.loan_contingency"))

@bp.route("/emprestimos/contingencia/<int:id>")
@login_required
def loan_contingency_detail(id):
    loan = db.get_or_404(ContingencyLoan, id)
    return render_template("loan_contingency_detail.html", loan=loan)

@bp.route("/emprestimos/contingencia/<int:id>/editar", methods=["GET", "POST"])
@login_required
def loan_contingency_edit(id):
    loan = db.get_or_404(ContingencyLoan, id)
    if request.method == "POST":
        date_str = request.form.get("loan_date")
        if date_str:
            loan.loan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
        loan.user_name = request.form["user_name"]; loan.user_document = request.form.get("user_document")
        loan.user_phone = request.form.get("user_phone"); loan.user_registration = request.form.get("user_registration")
        loan.notes = request.form.get("notes")
        due = request.form.get("expected_return_date")
        loan.expected_return_date = datetime.strptime(due, "%Y-%m-%d").date() if due else None
        
        for item in loan.items: db.session.delete(item)
        db.session.flush()
        
        book_titles = request.form.getlist("book_title[]"); copy_codes = request.form.getlist("copy_code[]"); item_notes = request.form.getlist("item_notes[]")
        for i in range(len(book_titles)):
            if book_titles[i].strip():
                db.session.add(ContingencyLoanItem(loan_id=loan.id, book_title=book_titles[i], copy_code=copy_codes[i] if i < len(copy_codes) else "", item_notes=item_notes[i] if i < len(item_notes) else ""))
        db.session.commit(); flash("Empréstimo atualizado!", "success")
        return redirect(url_for("main.loan_contingency_detail", id=loan.id))
    return render_template("loan_contingency_edit.html", loan=loan)

@bp.route("/emprestimos/contingencia/<int:id>/excluir", methods=["POST"])
@login_required
def loan_contingency_delete(id):
    loan = db.get_or_404(ContingencyLoan, id)
    db.session.delete(loan); db.session.commit()
    flash("Empréstimo excluído.", "success")
    return redirect(url_for("main.loan_contingency"))

@bp.route("/emprestimos/contingencia/<int:id>/pdf")
@login_required
def loan_contingency_pdf(id):
    loan = db.get_or_404(ContingencyLoan, id)
    buffer = BytesIO(); p = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    p.setFont("Helvetica-Bold", 16); p.drawString(50, height - 50, "COMPROVANTE DE EMPRÉSTIMO")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, f"Data do Empréstimo: {loan.loan_date.strftime('%d/%m/%Y')} | Operador: {loan.operator.name}")
    p.drawString(50, height - 85, f"Status Atual: {loan.status}")
    if loan.returned_at: p.drawString(50, height - 100, f"Data da Devolução: {loan.returned_at.strftime('%d/%m/%Y %H:%M')}")
    
    p.setFont("Helvetica-Bold", 12); p.drawString(50, height - 130, "DADOS DO SOLICITANTE"); p.line(50, height - 135, 545, height - 135)
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 155, f"Nome: {loan.user_name} | CPF: {loan.user_document or '-'}")
    p.drawString(50, height - 170, f"Cód. Pessoa: {loan.user_registration or '-'} | Tel: {loan.user_phone or '-'}")
    if loan.expected_return_date: p.drawString(50, height - 185, f"Devolução Prevista: {loan.expected_return_date.strftime('%d/%m/%Y')}")
    
    y = height - 215; p.setFont("Helvetica-Bold", 12); p.drawString(50, y, "LIVROS EMPRESTADOS"); p.line(50, y - 5, 545, y - 5)
    y -= 25; p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Título"); p.drawString(350, y, "C.E."); p.drawString(450, y, "OBS")
    p.setFont("Helvetica", 10); y -= 20
    for item in loan.items:
        p.drawString(50, y, item.book_title[:50]); p.drawString(350, y, item.copy_code or "-"); p.drawString(450, y, item.item_notes[:15] if item.item_notes else "-")
        y -= 20
        if y < 100: p.showPage(); y = height - 50
    p.line(50, 80, 250, 80); p.drawString(80, 65, "Assinatura do Usuário")
    p.line(300, 80, 500, 80); p.drawString(340, 65, "Assinatura do Operador")
    p.save(); buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"emprestimo_{loan.id}.pdf", mimetype='application/pdf')

@bp.route("/emprestimos/contingencia/excel")
@login_required
def loan_contingency_excel():
    wb = Workbook(); ws = wb.active; ws.title = "Emprestimos"
    ws.append(["Data Empréstimo", "Usuário", "CPF", "Cód. Pessoa", "Livros", "Devolução Prevista", "Devolvido Em", "Status", "Operador"])
    for cell in ws[1]: cell.font = Font(bold=True)
    for loan in ContingencyLoan.query.order_by(ContingencyLoan.loan_date.desc()).all():
        livros = ", ".join([item.book_title for item in loan.items])
        dt_dev = loan.returned_at.strftime('%d/%m/%Y %H:%M') if loan.returned_at else ""
        ws.append([loan.loan_date.strftime('%d/%m/%Y'), loan.user_name, loan.user_document, loan.user_registration, livros, loan.expected_return_date.strftime('%d/%m/%Y') if loan.expected_return_date else "", dt_dev, loan.status, loan.operator.name])
    out = BytesIO(); wb.save(out); out.seek(0)
    return send_file(out, as_attachment=True, download_name="emprestimos.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==========================================
# INTER-BIBLIOTECAS
# ==========================================
@bp.route("/emprestimos/interbibliotecas", methods=["GET", "POST"])
@login_required
def loan_interlibrary():
    if request.method == "POST":
        date_str = request.form.get("loan_date")
        dt_loan = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        
        loan = InterLibraryLoan(
            loan_date=dt_loan,
            campus_origin=request.form.get("campus_origin", "").strip(),
            campus_destination=request.form.get("campus_destination", "").strip(),
            pergamum_status=request.form.get("pergamum_status", "Pendente"),
            requesting_library=request.form["requesting_library"], address=request.form.get("address"),
            phone=request.form.get("phone"), contact_person=request.form.get("contact_person"), contact_email=request.form.get("contact_email"),
            student_name=request.form.get("student_name"), student_registration=request.form.get("student_registration"),
            book_reference=request.form["book_reference"], copy_code=request.form.get("copy_code"),
            item_value=request.form.get("item_value"), notes=request.form.get("notes"),
            created_by_id=current_user.id, status="Pendente"
        )
        db.session.add(loan); db.session.commit(); flash("Empréstimo registrado!", "success")
        return redirect(url_for("main.loan_interlibrary"))
    
    query = InterLibraryLoan.query
    term = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    
    if term:
        like = f"%{term}%"
        query = query.filter(or_(InterLibraryLoan.requesting_library.ilike(like), InterLibraryLoan.campus_origin.ilike(like), InterLibraryLoan.campus_destination.ilike(like), InterLibraryLoan.student_name.ilike(like), InterLibraryLoan.student_registration.ilike(like)))
    if status_filter:
        query = query.filter(InterLibraryLoan.status == status_filter)
        
    rows = query.order_by(InterLibraryLoan.loan_date.desc(), InterLibraryLoan.id.desc()).all()
    return render_template("loan_interlibrary.html", rows=rows, term=term, status_filter=status_filter)

@bp.route("/emprestimos/interbibliotecas/<int:id>/devolver", methods=["POST"])
@login_required
def loan_interlibrary_return(id):
    loan = db.get_or_404(InterLibraryLoan, id)
    if loan.status != "Devolvido":
        loan.return_date = date.today()
        loan.status = "Devolvido"
        db.session.commit()
        flash("Devolução registrada com sucesso!", "success")
    return redirect(url_for("main.loan_interlibrary"))

@bp.route("/emprestimos/interbibliotecas/<int:id>")
@login_required
def loan_interlibrary_detail(id):
    loan = db.get_or_404(InterLibraryLoan, id)
    return render_template("loan_interlibrary_detail.html", loan=loan)

@bp.route("/emprestimos/interbibliotecas/<int:id>/editar", methods=["GET", "POST"])
@login_required
def loan_interlibrary_edit(id):
    loan = db.get_or_404(InterLibraryLoan, id)
    if request.method == "POST":
        date_str = request.form.get("loan_date")
        if date_str:
            loan.loan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
        loan.campus_origin = request.form.get("campus_origin", "").strip()
        loan.campus_destination = request.form.get("campus_destination", "").strip()
        loan.pergamum_status = request.form.get("pergamum_status", "Pendente")
        loan.requesting_library = request.form["requesting_library"]; loan.address = request.form.get("address")
        loan.phone = request.form.get("phone"); loan.contact_person = request.form.get("contact_person")
        loan.contact_email = request.form.get("contact_email"); loan.student_name = request.form.get("student_name")
        loan.student_registration = request.form.get("student_registration"); loan.book_reference = request.form["book_reference"]
        loan.copy_code = request.form.get("copy_code"); loan.item_value = request.form.get("item_value")
        loan.notes = request.form.get("notes")
        db.session.commit(); flash("Solicitação atualizada!", "success")
        return redirect(url_for("main.loan_interlibrary_detail", id=loan.id))
    return render_template("loan_interlibrary_edit.html", loan=loan)

@bp.route("/emprestimos/interbibliotecas/<int:id>/excluir", methods=["POST"])
@login_required
def loan_interlibrary_delete(id):
    loan = db.get_or_404(InterLibraryLoan, id)
    db.session.delete(loan); db.session.commit(); flash("Solicitação excluída.", "success")
    return redirect(url_for("main.loan_interlibrary"))

@bp.route("/emprestimos/interbibliotecas/<int:id>/pdf")
@login_required
def loan_interlibrary_pdf(id):
    loan = db.get_or_404(InterLibraryLoan, id)
    buffer = BytesIO(); p = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    p.setFont("Helvetica-Bold", 16); p.drawString(50, height - 50, "RECIBO DE EMPRÉSTIMO INTER-BIBLIOTECAS")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, f"Data do Empréstimo: {loan.loan_date.strftime('%d/%m/%Y') if loan.loan_date else '-'} | Operador: {loan.operator.name} | Status: {loan.status}")
    if loan.return_date: p.drawString(50, height - 85, f"Data da Devolução: {loan.return_date.strftime('%d/%m/%Y')}")
    
    p.setFont("Helvetica-Bold", 12); p.drawString(50, height - 115, "INSTITUIÇÃO SOLICITANTE"); p.line(50, height - 120, 545, height - 120)
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 140, f"Biblioteca: {loan.requesting_library}")
    p.drawString(50, height - 155, f"Endereço: {loan.address or '-'} | Tel: {loan.phone or '-'}")
    p.drawString(50, height - 170, f"Contato: {loan.contact_person or '-'} | E-mail: {loan.contact_email or '-'}")
    p.drawString(50, height - 190, f"Solicitante: {loan.student_name or '-'} | Matrícula: {loan.student_registration or '-'}")
    
    y = height - 225; p.setFont("Helvetica-Bold", 12); p.drawString(50, y, "INFORMAÇÕES DO ITEM"); p.line(50, y - 5, 545, y - 5)
    p.setFont("Helvetica", 10); y -= 25
    p.drawString(50, y, f"Referência: {loan.book_reference}"); y -= 20
    p.drawString(50, y, f"Cód. Exemplar: {loan.copy_code or '-'} | Valor: {loan.item_value or '-'}")
    if loan.notes: y -= 20; p.drawString(50, y, f"Observações: {loan.notes}")
    
    p.line(50, 80, 250, 80); p.drawString(80, 65, "Assinatura do Emprestador")
    p.line(300, 80, 500, 80); p.drawString(340, 65, "Assinatura do Solicitante")
    p.save(); buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"interbiblioteca_{loan.id}.pdf", mimetype='application/pdf')

@bp.route("/emprestimos/interbibliotecas/excel")
@login_required
def loan_interlibrary_excel():
    wb = Workbook(); ws = wb.active; ws.title = "Inter_Bibliotecas"
    ws.append(["Data Empréstimo", "Campus de Origem", "Campus de Destino", "Biblioteca", "Solicitante", "Matrícula", "Referência", "Devolvido Em", "Status", "Passado para Pergamum"])
    for cell in ws[1]: cell.font = Font(bold=True)
    for loan in InterLibraryLoan.query.order_by(InterLibraryLoan.loan_date.desc()).all():
        dt_dev = loan.return_date.strftime('%d/%m/%Y') if loan.return_date else ""
        ws.append([loan.loan_date.strftime('%d/%m/%Y') if loan.loan_date else "", loan.campus_origin or "", loan.campus_destination or "", loan.requesting_library, loan.student_name, loan.student_registration, loan.book_reference, dt_dev, loan.status, loan.pergamum_status or "Pendente"])
    out = BytesIO(); wb.save(out); out.seek(0)
    return send_file(out, as_attachment=True, download_name="interbibliotecas.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==========================================
# CHAT, NOTIFICAÇÕES E USUÁRIOS
# ==========================================
@bp.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            db.session.add(ChatMessage(user_id=current_user.id, body=body))
            db.session.commit(); return redirect(url_for("main.chat"))
    messages = ChatMessage.query.order_by(ChatMessage.created_at.asc()).limit(200).all()
    return render_template("chat.html", messages=messages)

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
    db.session.commit(); return redirect(url_for("main.notifications"))

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
            u.set_password(password); db.session.add(u)
            try:
                db.session.commit(); flash("Usuário criado.", "success")
            except IntegrityError:
                db.session.rollback(); flash("Login ou e-mail já utilizado.", "danger")
    return render_template("users.html", users=User.query.order_by(User.name).all())

@bp.route("/alterar-senha", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash("A sua senha atual está incorreta.", "danger")
        elif new_password != confirm_password:
            flash("A nova senha e a confirmação não coincidem.", "danger")
        elif len(new_password) < 10:
            flash("A nova senha precisa ter pelo menos 10 caracteres.", "danger")
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash("Sua senha foi alterada com sucesso!", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("change_password.html")