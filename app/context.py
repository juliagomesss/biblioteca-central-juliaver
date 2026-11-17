from datetime import date
from flask_login import current_user
from sqlalchemy import and_

def inject_globals():
    unread_notifications = 0
    unread_activities = 0
    if current_user.is_authenticated:
        # Importações atualizadas para o novo modelo
        from .models import Notification, NotificationRead, Activity
        from .extensions import db
        
        unread_notifications = Notification.query.filter(
            Notification.resolved_at.is_(None),
            ~Notification.reads.any(NotificationRead.user_id == current_user.id),
        ).count()
        
        # Conta atividades que não estão concluídas
        unread_activities = Activity.query.filter(Activity.status != "Concluída").count()

    return {
        "now_date": date.today().strftime("%d/%m/%Y"),
        "today": date.today(),
        "unread_notifications_count": unread_notifications,
        "unread_activities_count": unread_activities,
    }