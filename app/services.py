from datetime import date, datetime, timedelta
from .extensions import db
from .models import *

def audit(user, action, entity, entity_id=None, details=None):
    db.session.add(AuditLog(user_id=user.id if user else None, action=action,
                            entity=entity, entity_id=entity_id, details=details))

def refresh_notifications():
    # Como removemos os livros, as notificações agora são focadas em Atividades
    today = date.today()
    
    # Notifica atividades urgentes que foram criadas hoje ou estão pendentes há muito tempo
    pending_activities = Activity.query.filter(Activity.status != "Concluída").all()
    
    for act in pending_activities:
        if act.priority in ["Alta", "Urgente"]:
            exists = Notification.query.filter_by(kind="atividade_urgente", message=f"Atividade pendente: {act.title}").first()
            if not exists:
                db.session.add(Notification(kind="atividade_urgente", message=f"Atividade pendente: {act.title}"))
    
    db.session.commit()