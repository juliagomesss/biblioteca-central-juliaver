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

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="Normal")
    status = db.Column(db.String(30), nullable=False, default="Aberta")
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creator = db.relationship("User")

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    author = db.relationship("User")

class ContingencyLoan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_date = db.Column(db.Date, nullable=False, default=date.today)
    expected_return_date = db.Column(db.Date)
    user_document = db.Column(db.String(20))
    user_name = db.Column(db.String(140), nullable=False)
    user_phone = db.Column(db.String(40))
    user_registration = db.Column(db.String(60))
    notes = db.Column(db.Text)
    
    # NOVOS CAMPOS
    returned_at = db.Column(db.DateTime, nullable=True) 
    status = db.Column(db.String(30), default="Emprestado", nullable=False) # Emprestado, Devolvido, Atrasado
    
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    operator = db.relationship("User")
    items = db.relationship("ContingencyLoanItem", backref="loan", cascade="all, delete-orphan")

class ContingencyLoanItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("contingency_loan.id"), nullable=False)
    book_title = db.Column(db.String(220), nullable=False)
    copy_code = db.Column(db.String(60))
    item_notes = db.Column(db.Text)

class InterLibraryLoan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_date = db.Column(db.Date, nullable=False, default=date.today)
    loan_date = db.Column(db.Date)
    return_date = db.Column(db.Date)
    
    # NOVO CAMPO
    status = db.Column(db.String(30), default="Pendente", nullable=False) # Pendente, Emprestado, Devolvido
    
    campus_origin = db.Column(db.String(140))
    campus_destination = db.Column(db.String(140))
    pergamum_status = db.Column(db.String(20), nullable=False, default="Pendente") # Sim, Pendente
    requesting_library = db.Column(db.String(140), nullable=False)
    address = db.Column(db.String(255))
    phone = db.Column(db.String(40))
    contact_person = db.Column(db.String(140))
    contact_email = db.Column(db.String(160))
    
    student_name = db.Column(db.String(140)) 
    student_registration = db.Column(db.String(60))
    
    book_reference = db.Column(db.String(255), nullable=False)
    copy_code = db.Column(db.String(60))
    item_value = db.Column(db.String(40))
    notes = db.Column(db.Text)
    
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    operator = db.relationship("User")

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