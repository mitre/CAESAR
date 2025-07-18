# -*- coding: utf-8 -*-
"""Click commands."""
import os

import click
from flask.cli import AppGroup
from flask.cli import with_appcontext
from flask_security.utils import hash_password

from enferno.extensions import db
from enferno.user.models import User, Role
from enferno.utils.data_helpers import import_default_data, generate_user_roles, generate_workflow_statues, create_default_location_data

@click.command()
@click.option('--create-exts', is_flag=True)
@with_appcontext
def create_db(create_exts):
    """
    Creates db tables - import your models within commands.py to create the models.
    """
    # create db exts if required, needs superuser db permissions
    if create_exts:
        db.engine.execute('CREATE EXTENSION if not exists pg_trgm ;')
        click.echo('Trigram extension installed successfully')
        db.engine.execute('CREATE EXTENSION if not exists postgis ;')
        click.echo('Postgis extension installed successfully')

    db.create_all()
    click.echo('Database structure created successfully')
    generate_user_roles()
    click.echo('Generated user roles successfully.')
    generate_workflow_statues()
    click.echo('Generated system workflow statues successfully.')
    create_default_location_data()
    click.echo('Generated location metadata successfully.')

@click.command()
@with_appcontext
def import_data():
    """
    Imports default Bayanat data for lists and relationship types.
    """
    try:
        import_default_data()
        click.echo('Imported data successfully.')
    except:
        click.echo('Error importing data.')

@click.command()
@click.option('--username', default="admin", help="Username for the admin user")
@click.option('--password', help="Password for the admin user")
@with_appcontext
def install(password, username):
    """Install a default Admin user and add an Admin role to it.
    """
    admin_role = Role.query.filter(Role.name == 'Admin').first()

    # check if there's an existing admin
    if admin_role.users.all():
        click.echo('An admin user is already installed.')
        return

    # to make sure username doesn't already exist
    while True:
        if username:
            u = username
        else:
            u = click.prompt('Admin username?', default='admin')
    
        check = User.query.filter(User.username == u.lower()).first()
        if check is not None:
            click.echo('Username already exists.')
        else:
            break

    if password:
        p = password
    else:
        p = click.prompt('Admin Password?', hide_input=True)
    
    user = User(username=u, password=hash_password(p), active=1)
    user.name = 'Admin'
    user.roles.append(admin_role)
    check = user.save()
    if check:
        click.echo('Admin user installed successfully.')
    else:
        click.echo('Error installing admin user.')


@click.command()
@click.option('-u', '--username', prompt=True, default=None)
@click.option('-p', '--password', prompt=True, default=None, hide_input=True)
@with_appcontext
def create(username, password):
    """Creates a user.
    """
    if len(username) < 4:
        click.echo('Username must be at least 4 characters long')
        return
    user = User.query.filter(User.username == username).first()
    if user:
        click.echo('User already exists!')
        return
    if len(password < 8):
        click.echo('Password should be at least 8 characters long!')
        return
    user = User(username=username, password=hash_password(password), active=1)
    if user.save():
        click.echo('User created successfully')
    else:
        click.echo('Error creating user.')


@click.command()
@click.option('-u', '--username', prompt=True, default=None)
@click.option('-r', '--role', prompt=True, default='Admin')
@with_appcontext
def add_role(username, role):
    """Adds a role to the specified user.
    """
    from enferno.user.models import Role
    user = User.query.filter(User.username == username).first()

    if not user:
        click.echo('Sorry, this user does not exist!')
    else:
        r = Role.query.filter(Role.name == role).first()
        if not role:
            click.echo('Sorry, this role does not exist!')
            u = click.prompt('Would you like to create one? Y/N', default='N')
            if u.lower() == 'y':
                r = Role(name=role).save()
        # add role to user
        user.roles.append(r)
        click.echo('Role {} added successfully to user {}'.format(username, role))


@click.command()
@click.option('-u', '--username', prompt=True, default=None)
@click.option('-p', '--password', hide_input=True, confirmation_prompt=True, prompt=True, default=None)
@with_appcontext
def reset(username, password):
    """Reset a user password
    """
    user = User.query.filter(User.username == username).first()
    if not user:
        click.echo('Specified user does not exist!')
    else:
        if len(password) < 8:
            click.echo('Password should be at least 8 characters long!')
            return
        user.password = hash_password(password)
        user.save()
        click.echo('User password has been reset successfully.')
        if not user.active:
            click.echo('Warning: User is not active!')


@click.command()
def clean():
    """Remove *.pyc and *.pyo files recursively starting at current directory.
    Borrowed from Flask-Script, converted to use Click.
    """
    for dirpath, dirnames, filenames in os.walk('.'):
        for filename in filenames:
            if filename.endswith('.pyc') or filename.endswith('.pyo'):
                full_pathname = os.path.join(dirpath, filename)
                click.echo('Removing {}'.format(full_pathname))
                os.remove(full_pathname)


# translation management
i18n_cli = AppGroup('translate', short_help='commands to help with translation management')


@i18n_cli.command()
def extract():
    if os.system('pybabel extract -F babel.cfg -k _l -o messages.pot .'):
        raise RuntimeError('Extract command failed')


@i18n_cli.command()
def update():
    if os.system('pybabel update -i messages.pot -d enferno/translations'):
        raise RuntimeError('Update command failed')


@i18n_cli.command()
def compile():
    if os.system('pybabel compile -d enferno/translations'):
        raise RuntimeError('Compile command failed')
