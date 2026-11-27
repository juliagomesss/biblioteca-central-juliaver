import os
from flask import Flask, redirect, url_for, flash
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from config import Config
from .extensions import db
from .models import User
from .routes import bp

login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    flash("Faça login para acessar o sistema.", "warning")
    return redirect(url_for("main.login"))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"
    migrate.init_app(app, db)
    csrf.init_app(app)
    app.register_blueprint(bp)
    from .commands import register_commands
    register_commands(app)
    from .context import inject_globals
    app.context_processor(inject_globals)
    with app.app_context():
        from . import models
        if app.config.get("AUTO_CREATE_DB", True):
            db.create_all()
            # Compatibilidade com bancos já existentes: db.create_all() não adiciona colunas.
            inspector = inspect(db.engine)
            if "inter_library_loan" in inspector.get_table_names():
                existing_columns = {column["name"] for column in inspector.get_columns("inter_library_loan")}
                new_columns = {
                    "campus_origin": "VARCHAR(140)",
                    "campus_destination": "VARCHAR(140)",
                    "pergamum_status": "VARCHAR(20) NOT NULL DEFAULT 'Pendente'",
                }
                with db.engine.begin() as connection:
                    for column_name, column_type in new_columns.items():
                        if column_name not in existing_columns:
                            connection.execute(text(
                                f"ALTER TABLE inter_library_loan ADD COLUMN {column_name} {column_type}"
                            ))
    return app
