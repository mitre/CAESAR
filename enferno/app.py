# -*- coding: utf-8 -*-

import pandas as pd
import os
from flask import Flask, render_template, current_app, request
from flask_security import current_user
from flask_login import user_logged_in, user_logged_out
from flask_security import Security, SQLAlchemyUserDatastore, UsernameUtil
from flask_migrate import Migrate
import re
import unicodedata

import enferno.commands as commands
from enferno.admin.models import Bulletin, Label, Source, Location, Event, Eventtype, Media, Btob, Actor, Atoa, Atob, \
    Incident, Itoa, Itob, Itoi, BulletinHistory, Activity, Settings, GeoLocation
from enferno.user.models import WebAuthn
from enferno.admin.views import admin
from enferno.data_import.views import imports
from enferno.extensions import cache, db, session, bouncer, babel, rds
from enferno.public.views import bp_public
from enferno.settings import Config
from enferno.user.forms import ExtendedRegisterForm
from enferno.user.models import User, Role
from enferno.user.views import bp_user
from apiflask import APIFlask
from flask_swagger_ui import get_swaggerui_blueprint

class CustomUsernameUtil(UsernameUtil):
    def check_username(self, username: str) -> str | None:
        
        # validate disallowed characters
        cats = [unicodedata.category(c)[0] for c in username]
        if any(cat not in ["L", "N"] and c != "." and c != "-" for cat, c in zip(cats, username)):
            return 'Disallowed characters detected'
        
        if (username.startswith('.') or username.startswith('-')):
            return 'Illegal character detected at beginning of username'
        
        if (username.endswith('.') or username.endswith('-')):
            return 'Illegal characted detected at end of username'
        
        return None

def get_locale():
    """
    Sets the system global language.
    :return: system language from the current session.
    """
    from flask import session
    # override = request.args.get('lang')
    # if override:
    #     session['lang'] = override
    default = 'en'
    try:
        default = current_app.config.get('BABEL_DEFAULT_LOCALE')
    except Exception as e:
        print(e)

    if not current_user:
        # working outside of a session context
        return default
    if not current_user.is_authenticated:
        # will return default language
        pass
    else:
        if current_user.settings:
            if current_user.settings.get('language'):
                session['lang'] = current_user.settings.get('language')
    return session.get('lang', default)

def create_app(config_object=Config):
    if config_object.ENV == 'dev':
        # Use APIFlask instead of `Flask` so it generates an Open API spec
        app = APIFlask(__name__, spec_path='/openapi.yaml')
        register_openapi_docs(app)
    else:
        app = Flask(__name__)
    
    app.config.from_object(config_object)
    register_blueprints(app)
    register_extensions(app)

    register_errorhandlers(app)
    register_shellcontext(app)
    register_commands(app)
    register_signals(app)
    register_version(app)
    return app

def register_extensions(app):
    cache.init_app(app)
    db.init_app(app)
    Migrate(app, db)
    user_datastore = SQLAlchemyUserDatastore(db, User, Role,webauthn_model=WebAuthn)
    security = Security(app, user_datastore,
                        register_form=ExtendedRegisterForm,
                        username_util_cls=CustomUsernameUtil
    )
    session.init_app(app)
    bouncer.init_app(app)
    babel.init_app(app, locale_selector=get_locale, default_domain='messages', default_locale='en')
    rds.init_app(app)

    return None


def register_signals(app):
    @user_logged_in.connect_via(app)
    def _after_login_hook(sender, user, **extra):
        # clear login counter
        from flask import session
        if session.get('failed'):
            session.pop('failed')
            print('login counter cleared')

        Activity.create(user, Activity.ACTION_LOGIN, user.to_mini(), 'user')

    @user_logged_out.connect_via(app)
    def _after_logout_hook(sender, user, **extra):
        Activity.create(user, Activity.ACTION_LOGOUT, user.to_mini(), 'user')


def register_blueprints(app):
    app.register_blueprint(bp_public)
    app.register_blueprint(bp_user)
    app.register_blueprint(admin)
    app.register_blueprint(imports)

    if app.config.get('EXPORT_TOOL'):
        try:
            from enferno.export.views import export
            app.register_blueprint(export)
        except ImportError as e:
            print(e)

    if app.config.get('DEDUP_TOOL'):
        try:
            from enferno.deduplication.views import deduplication
            app.register_blueprint(deduplication)
        except ImportError as e:
            print(e)

    return None


def register_errorhandlers(app):
    def render_error(error):
        error_code = getattr(error, 'code', 500)
        return render_template("views/errors/{0}.html".format(error_code)), error_code

    for errcode in [401, 404, 500]:
        app.errorhandler(errcode)(render_error)
    return None


def register_shellcontext(app):
    """Register shell context objects."""

    def shell_context():
        """Shell context objects."""
        return {
            'db': db,
            'pd': pd,
            'User': User,
            'Role': Role,
            'Label': Label,
            'Bulletin': Bulletin,
            'BulletinHistory': BulletinHistory,
            'Location': Location,
            'GeoLocation': GeoLocation,
            'Source': Source,
            'Eventtype': Eventtype,
            'Event': Event,
            'Media': Media,
            'Btob': Btob,
            'Atoa': Atoa,
            'Atob': Atob,
            'Actor': Actor,
            'Incident': Incident,
            'Itoi': Itoi,
            'Itob': Itob,
            'Itoa': Itoa,
            'Activity': Activity,
            'Settings': Settings,
            'rds': rds
        }

    app.shell_context_processor(shell_context)


def register_commands(app):
    """Register Click commands."""

    app.cli.add_command(commands.clean)
    app.cli.add_command(commands.create_db)
    app.cli.add_command(commands.import_data)
    app.cli.add_command(commands.install)
    app.cli.add_command(commands.create)
    app.cli.add_command(commands.add_role)
    app.cli.add_command(commands.reset)
    app.cli.add_command(commands.i18n_cli)

def register_openapi_docs(app):
    # Setup Swagger UI to display OpenAPI spec
    swaggerui_blueprint = get_swaggerui_blueprint(
        '/api/docs', 
        '/openapi.yaml',
        config={
            'app_name': "CAESAR"
        },
    )

    app.register_blueprint(swaggerui_blueprint)
    app.config['SPEC_FORMAT'] = 'yaml'

def register_version(app):
    try:
        version_file_path = os.path.abspath('__version__')
        with open(version_file_path) as file:
            app.config['CAESAR_VERSION'] = file.read()
    except FileNotFoundError:
        app.config['CAESAR_VERSION'] = '1.0.0'
