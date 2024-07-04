import os

from flask import Flask
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)

csrf = CSRFProtect(app)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "secret string")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:////" + os.path.join(app.root_path, "../data.db"),
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# no cache
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

app.config['DEBUG'] = True

# app.jinja_env.cache = {}

from portfolio.models import db
from flask_migrate import Migrate

db.init_app(app)
migrate = Migrate(app, db, render_as_batch=True)

import portfolio.handlers
import portfolio.views
