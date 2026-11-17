from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="servidor")
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    @property
    def is_active(self): return self.active

# --- ÁREA DE ATIVIDADES ---
class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="Normal")
    status = db.Column(db.String(30), nullable=False, default="Aberta")
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creator = db.relationship("User")

# --- CHAT GERAL ---
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    author = db.relationship("User")

# --- EMPRÉSTIMO: CONTINGÊNCIA (Alunos) ---
class ContingencyLoan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Dados do Cabeçalho (Imagem 2 e Imagem 4 do Pergamum)
    loan_date = db.Column(db.Date, nullable=False, default=date.today) # Data
    expected_return_date = db.Column(db.Date) # Devolução prevista
    user_document = db.Column(db.String(20)) # CPF
    user_name = db.Column(db.String(140), nullable=False) # Usuário(a) / Nome do patrono
    user_phone = db.Column(db.String(40)) # TEL/Cel
    user_registration = db.Column(db.String(60)) # Código Pessoa (Pergamum)
    notes = db.Column(db.Text) # OBS geral
    
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    operator = db.relationship("User")
    items = db.relationship("ContingencyLoanItem", backref="loan", cascade="all, delete-orphan")

class ContingencyLoanItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("contingency_loan.id"), nullable=False)
    # Campos de cada livro (Imagem 2)
    book_title = db.Column(db.String(220), nullable=False) # Livro
    copy_code = db.Column(db.String(60)) # C.E. (Código do Exemplar)
    item_notes = db.Column(db.Text) # OBS (do livro)

# --- EMPRÉSTIMO: INTER-BIBLIOTECAS ---
class InterLibraryLoan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Colunas da Imagem 1 (Excel)
    request_date = db.Column(db.Date, nullable=False, default=date.today) # Data Solicitação
    loan_date = db.Column(db.Date) # Data Empréstimo
    return_date = db.Column(db.Date) # Data Devolução
    
    requesting_library = db.Column(db.String(140), nullable=False) # Biblioteca (Solicitante)
    address = db.Column(db.String(255)) # Endereço
    phone = db.Column(db.String(40)) # Telefone
    contact_person = db.Column(db.String(140)) # Contato
    contact_email = db.Column(db.String(160)) # E-mail
    
    book_reference = db.Column(db.String(255), nullable=False) # Referência Bibliográfica
    copy_code = db.Column(db.String(60)) # Código do Exemplar
    item_value = db.Column(db.String(40)) # Valor do item
    notes = db.Column(db.Text) # Observações
    
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    operator = db.relationship("User")

# --- NOTIFICAÇÕES E AUDITORIA ---
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reads = db.relationship("NotificationRead", cascade="all, delete-orphan", backref="notification")

class NotificationRead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey("notification.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("notification_id", "user_id", name="uq_notification_user"),)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(60), nullable=False)
    entity = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)