from flask import request, redirect, send_from_directory
from apiflask import APIBlueprint

bp_public = APIBlueprint('public', __name__, static_folder='../static')


@bp_public.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'public, max-age=10800'
    return response

@bp_public.route('/')
def index():
    return redirect('/dashboard')

@bp_public.route('/robots.txt')
def static_from_root():
    return send_from_directory(bp_public.static_folder, request.path[1:])

from enferno.extensions import db
@bp_public.teardown_app_request
def shutdown_global_session(exception=None):
    try:
        #print ('-------------------- session cleaned --------------------')
        db.session.remove()
    except Exception as e:
        print (e)