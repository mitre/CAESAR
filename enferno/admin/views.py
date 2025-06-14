import hashlib
import os
import shutil
from datetime import datetime, timedelta
import unicodedata
from uuid import uuid4
from sqlalchemy.orm import aliased
from zxcvbn import zxcvbn
import bleach
import boto3
import passlib
import shortuuid
import re
from flask import request, abort, Response, current_app, json, g, send_file, send_from_directory
from flask.templating import render_template
from flask_babel import gettext
from flask_bouncer import requires
from flask_security.decorators import auth_required, current_user, roles_accepted, roles_required
from sqlalchemy import and_, desc, or_, cast, String
from werkzeug.utils import safe_join
from werkzeug.utils import secure_filename

from enferno.admin.models import (ActorSubType, Author, Bulletin, ConsentUse, Label, Organization, OrganizationHistory,
                                  OrganizationRole, OrganizationType, OtoaInfo, OtobInfo, OtoiInfo, OtooInfo, Source, 
                                  Location, Eventtype, Media, Actor, Incident, IncidentHistory, BulletinHistory, 
                                  ActorHistory, LocationHistory, PotentialViolation, ClaimedViolation,
                                  Activity, Query, LocationAdminLevel, LocationType, AppConfig,
                                  AtobInfo, AtoaInfo, BtobInfo, ItoiInfo, ItoaInfo, ItobInfo, Country, Ethnography,
                                  MediaCategory, GeoLocation, GeoLocationType, WorkflowStatus, SocialMediaPlatform, SocialMediaHandle,
                                  SanctionRegime)
from enferno.extensions import bouncer, rds
from enferno.extensions import cache
from enferno.tasks import bulk_update_bulletins, bulk_update_actors, bulk_update_incidents, bulk_update_organizations
from enferno.user.models import User, Role
from enferno.utils.config_utils import ConfigManager
from enferno.utils.http_response import HTTPResponse
from enferno.utils.search_utils import SearchUtils
from apiflask import APIBlueprint

root = os.path.abspath(os.path.dirname(__file__))
admin = APIBlueprint('admin', __name__,
                  template_folder=os.path.join(root, 'templates'),
                  static_folder=os.path.join(root, 'static'),
                  url_prefix='/admin')

#TODO: probably move this to somewhere else and import
relation_classes = ['actor', 'incident', 'bulletin', 'organization']

# default global items per page
PER_PAGE = 30
REL_PER_PAGE = 5


@admin.before_request
@auth_required('session')
def before_request():
    """
    Attaches the user object to all requests
    and a version number that is used to clear the static files cache globally.
    :return: None
    """
    g.user = current_user
    g.version = '5'


@admin.app_context_processor
def ctx():
    """
    passes all users to the application, based on the current user's permissions.
    :return: None
    """
    users = User.query.order_by(User.username).all()
    if current_user and current_user.is_authenticated:
        users = [u.to_compact() for u in users]
        return {'users': users}
    return {}


@bouncer.authorization_method
def define_authorization(user, ability):
    """
    Defines users abilities based on their stored permissions.
    :param user: system user
    :param ability: used to restrict/allow what a user can do
    :return: None
    """
    if user.view_usernames:
        ability.can('view', 'usernames')
    if user.view_simple_history or user.view_full_history:
        ability.can('view', 'history')
    # if user.has_role('Admin'):
    #     ability.can('edit', 'Bulletin')
    # else:
    #     def if_assigned(bulletin):
    #         return bulletin.assigned_to_id == user.id

    #     ability.can('edit', Bulletin, if_assigned)


@admin.route('/dashboard')
def dashboard():
    """
    Endpoint to render the dashboard.
    :return: html template for dashboard.
    """
    return render_template('index.html')

@admin.route('/search/')
def global_search():
    """
    Endpoint to render the global search.
    :return: html template for global search.
    """
    return render_template('views/admin/search.html')


# Labels routes
@admin.route('/labels/')
@roles_accepted('Admin', 'Mod')
def labels():
    """
    Endpoint to render the labels backend page.
    :return: html template for labels management.
    """
    return render_template('views/admin/labels.html')


@admin.route('/api/labels/')
def api_labels():
    """
    API endpoint feed and filter labels with paging
    :return: json response of label objects.
    """
    query = []
    q = request.args.get('q', None)

    if q:
        words = q.split(' ')
        query.extend([Label.title.ilike(F'%{word}%') for word in words])

    typ = request.args.get('typ', None)
    if typ and typ in ['for_bulletin', 'for_actor', 'for_incident', 'for_offline']:
        query.append(
            getattr(Label, typ) == True
        )
    fltr = request.args.get('fltr', None)

    if fltr == 'verified':
        query.append(
            Label.verified == True
        )
    elif fltr == 'all':
        pass
    else:
        query.append(
            Label.verified == False
        )

    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    # pull children only when specific labels are searched
    if q:
        result = Label.query.filter(*query).all()
        labels = [label for label in result]
        ids = []
        children = Label.get_children(labels)
        for label in labels + children:
            ids.append(label.id)
        # remove dups
        ids = list(set(ids))
        result = Label.query.filter(
            Label.id.in_(ids))
    else:
        result = Label.query.filter(*query)

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'

    #Adjust query for sorting by a field in a related model if needed
    if sort_by == 'parent.title':
        parent_alias = aliased(Label)
        result = result.outerjoin(parent_alias, Label.parent_label_id == parent_alias.id)
        result = result.order_by(parent_alias.title.desc() if sort_desc else parent_alias.title)
    else:
        if hasattr(Label, sort_by):
            result = result.order_by(getattr(Label, sort_by).desc() if sort_desc else getattr(Label, sort_by))
        else:
            return {'error': 'Invalid sort_by fied'}, 400

    result = result.paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict(request.args.get('mode', 1)) for item in result.items], 'perPage': per_page,
                'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/label/')
@roles_accepted('Admin', 'Mod')
def api_label_create():
    """
    Endpoint to create a label.
    :return: success/error based on the operation result.
    """
    label = Label()
    created = label.from_json(request.json['item'])
    if created.save():
        return F'Created Label #{label.id}', 200
    else:
        return 'Save Failed', 417


@admin.put('/api/label/<int:id>')
@roles_accepted('Admin', 'Mod')
def api_label_update(id):
    """
    Endpoint to update a label.
    :param id: id of the label
    :return: success/error based on the operation result.
    """
    label = Label.query.get(id)
    if label is not None:
        label = label.from_json(request.json['item'])
        label.save()
        return F'Saved Label #{label.id}', 200
    else:
        return HTTPResponse.NOT_FOUND


@admin.delete('/api/label/<int:id>')
@roles_required('Admin')
def api_label_delete(id):
    """
    Endpoint to delete a label.
    :param id: id of the label
    :return: Success/error based on operation's result.
    """
    label = Label.query.get(id)
    label.delete()
    return F'Deleted Label #{label.id}', 200


@admin.post('/api/label/import/')
@roles_required('Admin')
def api_label_import():
    """
    Endpoint to import labels via CSV
    :return: Success/error based on operation's result.
    """
    if 'csv' in request.files:
        Label.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400


# EventType routes
@admin.route('/eventtypes/')
@roles_accepted('Admin', 'Mod')
def eventtypes():
    """
    Endpoint to render event types backend
    :return: html template of the event types backend
    """
    return render_template('views/admin/eventtypes.html')


@admin.route('/api/eventtypes/')
def api_eventtypes():
    """
    API endpoint to serve json feed of even types with paging support
    :return: json feed/success or error/404 based on request data
    """
    query = []
    q = request.args.get('q', None)
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    if q is not None:
        query.append(Eventtype.title.ilike('%' + q + '%'))

    typ = request.args.get('typ', None)
    if typ and typ in ['for_bulletin', 'for_actor']:
        query.append(
            getattr(Eventtype, typ) == True
        )
    result = Eventtype.query.filter(*query)

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'
    if hasattr(Eventtype, sort_by):
        result = result.order_by(getattr(Eventtype, sort_by).desc() if sort_desc else getattr(Eventtype, sort_by))
    else:
        return {'error': 'Invalid sort_by fied'}, 400
    result = result.paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/eventtype/')
@roles_accepted('Admin', 'Mod')
def api_eventtype_create():
    """
    Endpoint to create an Event Type
    :return: Success/Error based on operation's result
    """
    eventtype = Eventtype()
    created = eventtype.from_json(request.json['item'])
    if created.save():
        return F'Created Event #{eventtype.id}', 200
    else:
        return 'Save Failed', 417


@admin.put('/api/eventtype/<int:id>')
@roles_accepted('Admin', 'Mod')
def api_eventtype_update(id):
    """
    Endpoint to update an Event Type
    :param id: id of the item to be updated
    :return: success/error based on the operation's result
    """
    eventtype = Eventtype.query.get(id)
    if eventtype is None:
        return HTTPResponse.NOT_FOUND

    eventtype = eventtype.from_json(request.json['item'])
    eventtype.save()
    return F'Saved Event #{eventtype.id}', 200


@admin.delete('/api/eventtype/<int:id>')
@roles_required('Admin')
def api_eventtype_delete(id):
    """
    Endpoint to delete an event type
    :param id: id of the item
    :return: success/error based on the operation's result
    """
    eventtype = Eventtype.query.get(id)
    if eventtype is None:
        return HTTPResponse.NOT_FOUND

    eventtype.delete()
    return F'Deleted Event #{eventtype.id}', 200


@admin.post('/api/eventtype/import/')
@roles_required('Admin')
def api_eventtype_import():
    """
    Endpoint to bulk import event types from a CSV file
    :return: success/error based on the operation's result
    """
    if 'csv' in request.files:
        Eventtype.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400


@admin.route('/api/potentialviolation/', defaults={'page': 1})
@admin.route('/api/potentialviolation/<int:page>/')
def api_potentialviolations(page):
    """
    API endpoint that feeds json data of potential violations with paging and search support
    :param page: db query offset
    :return: json feed / success or error based on the operation/request data
    """
    query = []
    q = request.args.get('q', None)
    per_page = request.args.get('per_page', PER_PAGE, int)
    if q is not None:
        query.append(PotentialViolation.title.ilike('%' + q + '%'))
    result = PotentialViolation.query.filter(
        *query).order_by(PotentialViolation.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': PER_PAGE, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/potentialviolation/')
@roles_accepted('Admin', 'Mod')
def api_potentialviolation_create():
    """
    Endpoint to create a potential violation
    :return: success/error based on operation's result
    """
    potentialviolation = PotentialViolation()
    created = potentialviolation.from_json(request.json['item'])
    if created.save():
        return F'Created Potential Violation #{potentialviolation.id}', 200
    else:
        return 'Save Failed', 417


@admin.put('/api/potentialviolation/<int:id>')
@roles_accepted('Admin', 'Mod')
def api_potentialviolation_update(id):
    """
    Endpoint to update a potential violation
    :param id: id of the item to be updated
    :return: success/error based on the operation's result
    """
    potentialviolation = PotentialViolation.query.get(id)
    if potentialviolation is None:
        return HTTPResponse.NOT_FOUND

    potentialviolation = potentialviolation.from_json(request.json['item'])
    potentialviolation.save()
    return F'Saved Potential Violation #{potentialviolation.id}', 200


@admin.delete('/api/potentialviolation/<int:id>')
@roles_required('Admin')
def api_potentialviolation_delete(id):
    """
    Endpoint to delete a potential violation
    :param id: id of the item to delete
    :return: success/error based on the operation's result
    """
    potentialviolation = PotentialViolation.query.get(id)
    if potentialviolation is None:
        return HTTPResponse.NOT_FOUND
    potentialviolation.delete()
    return F'Deleted Potential Violation #{potentialviolation.id}', 200


@admin.post('/api/potentialviolation/import/')
@roles_required('Admin')
def api_potentialviolation_import():
    """
    Endpoint to import potential violations from csv file
    :return: success/error based on operation's result
    """
    if 'csv' in request.files:
        PotentialViolation.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400


@admin.route('/api/claimedviolation/', defaults={'page': 1})
@admin.route('/api/claimedviolation/<int:page>')
def api_claimedviolations(page):
    """
    API endpoint to feed json items of claimed violations, supports paging and search
    :param page: db query offset
    :return: json feed / success or error code
    """
    query = []
    q = request.args.get('q', None)
    per_page = request.args.get('per_page', PER_PAGE, int)
    if q is not None:
        query.append(ClaimedViolation.title.ilike('%' + q + '%'))
    result = ClaimedViolation.query.filter(
        *query).order_by(ClaimedViolation.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': PER_PAGE, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/claimedviolation/')
@roles_accepted('Admin', 'Mod')
def api_claimedviolation_create():
    """
    Endpoint to create a claimed violation
    :return: success / error based on operation's result
    """
    claimedviolation = ClaimedViolation()
    created = claimedviolation.from_json(request.json['item'])
    if created.save():
        return F'Created Claimed Violation #{claimedviolation.id}', 200
    else:
        return 'Save Failed', 417


@admin.put('/api/claimedviolation/<int:id>')
@roles_accepted('Admin', 'Mod')
def api_claimedviolation_update(id):
    """
    Endpoint to update a claimed violation
    :param id: id of the item to update
    :return: success/error based on operation's result
    """
    claimedviolation = ClaimedViolation.query.get(id)
    if claimedviolation is None:
        return HTTPResponse.NOT_FOUND

    claimedviolation = claimedviolation.from_json(request.json['item'])
    claimedviolation.save()
    return F'Saved Claimed Violation #{claimedviolation.id}', 200


@admin.delete('/api/claimedviolation/<int:id>')
@roles_required('Admin')
def api_claimedviolation_delete(id):
    """
    Endpoint to delete a claimed violation
    :param id: id of the item to delete
    :return: success/ error based on operation's result
    """
    claimedviolation = ClaimedViolation.query.get(id)
    if claimedviolation is None:
        return HTTPResponse.NOT_FOUND

    claimedviolation.delete()
    return F'Deleted Claimed Violation #{claimedviolation.id}', 200


@admin.post('/api/claimedviolation/import/')
@roles_required('Admin')
def api_claimedviolation_import():
    """
    Endpoint to import claimed violations from a CSV file
    :return: success/error based on operation's result
    """
    if 'csv' in request.files:
        ClaimedViolation.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400


""" SOURCES ROUTES """
@admin.route('/sources/')
@roles_accepted('Admin', 'Mod')
def sources():
    """
    Endpoint to render sources backend page
    :return: html of the sources page
    """
    return render_template('views/admin/sources.html')


@admin.route('/api/sources/')
def api_sources():
    """
    API Endpoint to feed json data of sources, supports paging and search
    :return: json feed of sources or error code based on operation's result
    """
    query = []
    q = request.args.get('q', None)

    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    if q is not None:
        words = q.split(' ')
        query.extend([Source.title.ilike(F'%{word}%') for word in words])

    # ignore complex recursion when pulling all sources without filters
    if q:
        result = Source.query.filter(*query).all()
        sources = [source for source in result]
        ids = []
        children = Source.get_children(sources)
        for source in sources + children:
            ids.append(source.id)

        # remove dups
        ids = list(set(ids))

        result = Source.query.filter(
            Source.id.in_(ids))
    else:
        result = Source.query.filter(*query)

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'

    #Adjust query for sorting by a field in a related model if needed
    if sort_by == "parent.title":
        parent_alias = aliased(Source)
        result = result.outerjoin(parent_alias, Source.parent_id == parent_alias.id)
        result = result.order_by(parent_alias.title.desc() if sort_desc else parent_alias.title)
    else:
        if hasattr(Source, sort_by):
            result = result.order_by(getattr(Source, sort_by).desc() if sort_desc else getattr(Source, sort_by))
        else:
            return {'error': 'Invalid sort_by field'}, 400

    result = result.paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/source/')
@roles_accepted('Admin', 'Mod', 'DA')
def api_source_create():
    """
    Endpoint to create a source
    :return: success/error based on operation's result
    """
    source = Source()
    created = source.from_json(request.json['item'])
    if created.save():
        return F'Created Source #{source.id}', 200
    else:
        return 'Save Failed', 417

@admin.put('/api/source/<int:id>')
@roles_accepted('Admin', 'Mod')
def api_source_update(id):
    """
    Endpoint to update a source
    :param id: id of the item to update
    :return: success/error based on the operation's result
    """
    source = Source.query.get(id)
    if source is None:
        return HTTPResponse.NOT_FOUND

    source = source.from_json(request.json['item'])
    source.save()
    return F'Saved Source #{source.id}', 200


@admin.delete('/api/source/<int:id>')
@roles_required('Admin')
def api_source_delete(id):
    """
    Endopint to delete a source item
    :param id: id of the item to delete
    :return: success/error based on operation's result
    """
    source = Source.query.get(id)
    if source is None:
        return HTTPResponse.NOT_FOUND
    source.delete()
    return F'Deleted Source #{source.id}', 200


@admin.route('/api/source/import/', methods=['POST'])
@roles_required('Admin')
def api_source_import():
    """
    Endpoint to import sources from CSV data
    :return: success/error based on operation's result
    """
    if 'csv' in request.files:
        Source.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400

""" /SOURCES ROUTES """

""" AUTHORS ROUTES """

@admin.route('/authors/')
@roles_accepted('Admin', 'Mod')
def authors():
    """
    Endpoint to render authors backend page
    :return: html of the authors page
    """
    return render_template('views/admin/authors.html')

@admin.route('/api/authors/')
def api_authors():
    """
    API Endpoint to fetch Authors, supports paging and search
    :return: json of authors or error code based on operation's result
    """
    query = []
    q = request.args.get('q', None)

    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    if q is not None:
        words = q.split(' ')
        query.extend([Author.name.ilike(f'%{word}%') for word in words])

    result = Author.query.filter(*query)

    # Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'

    if hasattr(Author, sort_by):
        result = result.order_by(getattr(Author, sort_by).desc() if sort_desc else getattr(Author, sort_by))
    else:
        return {'error': 'Invalid sort_by field'}, 400
    
    result = result.paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'),200

@admin.post('/api/author/')
@roles_accepted('Admin', 'Mod', 'DA')
def api_author_create():
    """ 
    Endpoint to create an author
    :return: success or error message based on operation's result
    """
    author = Author()
    author.from_json(request.json['item'])
    result = author.save()

    if result:
        return Response(json.dumps(result.to_dict()), content_type='application/json'), 200
    else:
        return 'Error creating author', 417

@admin.put('/api/author/<int:id>')
@roles_accepted('Admin', 'Mod')
def api_author_update(id):
    """
    Endpoint to update an author
    :param id: id of the author to update
    :return: success/error based on the operation's result
    """
    author = Author.query.get(id)
    if author is None:
        return HTTPResponse.NOT_FOUND
    
    author = author.from_json(request.json['item'])
    author.save()
    return f'Saved Author #{author.id}', 200

@admin.delete('/api/author/<int:id>')
@roles_required('Admin')
def api_author_delete(id):
    """
    Endopint to delete an author
    :param id: id of the author to delete
    :return: success/error based on operation's result
    """
    author = Author.query.get(id)
    if author is None:
        return HTTPResponse.NOT_FOUND
    author.delete()
    return f'Deleted Author #{author.id}', 200

@admin.route('/api/author/import/', methods=['POST'])
@roles_required('Admin')
def api_author_import():
    """
    Endpoint to import authors from CSV data
    :return: success/error based on operation's result
    """
    if 'csv' in request.files:
        Author.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400

""" /AUTHORS ROUTES """

# locations routes

@admin.route('/locations/', defaults={'id': None})
@admin.route('/locations/<int:id>')
@roles_accepted('Admin', 'Mod', 'DA')
def locations(id):
    """Endpoint for locations management."""
    return render_template('views/admin/locations.html')


@admin.route('/api/locations/', methods=['POST', 'GET'])
def api_locations():
    """Returns locations in JSON format, allows search and paging."""
    query = []
    su = SearchUtils(request.json, cls='Location')
    query = su.get_query()
    result = Location.query.filter(*query)
    options = request.json.get('options')

    #Sort by request property
    sort_by = options.get('sortBy', [])
    sort_desc = options.get('sortDesc')[0] if options.get('sortDesc') else False
    if len(sort_by) <= 0:
        sort_by = 'id'
    else:
        sort_by = sort_by[0]
    if sort_by == 'full_string':
        sort_by = 'full_location'

    #Adjust query for sorting by a field in a related model if needed
    if sort_by == "parent.title":
        parent_alias = aliased(Location)
        result = result.outerjoin(parent_alias, Location.parent_id == parent_alias.id)
        result = result.order_by(parent_alias.title.desc() if sort_desc else parent_alias.title)
    elif sort_by == "location_type.title":
        result = result.outerjoin(LocationType, Location.location_type_id == LocationType.id)
        result = result.order_by(LocationType.title.desc() if sort_desc else LocationType.title)
    elif sort_by == "admin_level.title":
        result = result.outerjoin(LocationAdminLevel, Location.admin_level_id == LocationAdminLevel.id)
        result = result.order_by(LocationAdminLevel.title.desc() if sort_desc else LocationAdminLevel.title)
    else:
        if hasattr(Location, sort_by):
            result = result.order_by(getattr(Location, sort_by).desc() if sort_desc else getattr(Location, sort_by))
        else:
            return {'error': 'Invalid sort_by fied'}, 400
    page = options.get('page', 1)
    per_page = options.get('itemsPerPage', PER_PAGE)

    result = result.paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict_without_geometry() for item in result.items], 'perPage': per_page, 'total': result.total}

    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/location/')
@roles_accepted('Admin', 'Mod', 'DA')
def api_location_create():
    """Endpoint for creating locations."""

    if not current_user.roles_in(['Admin', 'Mod']) and not current_user.can_edit_locations:
        return 'User not allowed to create Locations', 400

    location = Location()
    location = location.from_json(request.json['item'])

    if location.save():
        location.full_location = location.get_full_string()
        location.id_tree = location.get_id_tree()
        location.create_revision()
        return F'Created Location #{location.id}', 200


@admin.put('/api/location/<int:id>')
@roles_accepted('Admin', 'Mod', 'DA')
def api_location_update(id):
    """Endpoint for updating locations. """

    if not current_user.roles_in(['Admin', 'Mod']) and not current_user.can_edit_locations:
        return 'User not allowed to create Locations', 400

    location = Location.query.get(id)
    if location is not None:
        location = location.from_json(request.json.get('item'))
        # we need to commit this change to db first, to utilize CTE
        if location.save():
            # then update the location full string
            location.full_location = location.get_full_string()
            location.id_tree = location.get_id_tree()
            location.create_revision()
            return F'Saved Location #{location.id}', 200
        else:
            return 'Save Failed', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/location/<int:id>')
@roles_required('Admin')
def api_location_delete(id):
    """Endpoint for deleting locations. """

    if request.method == 'DELETE':
        location = Location.query.get(id)
        location.delete()
        return F'Deleted Location #{location.id}', 200


@admin.post('/api/location/import/')
@roles_required('Admin')
def api_location_import():
    """Endpoint for importing locations."""
    if 'csv' in request.files:
        Location.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400


# get one location
@admin.get('/api/location/<int:id>')
def api_location_get(id):
    """
    Endpoint to get a single location
    :param id: id of the location
    :return: location in json format / success or error
    """
    location = Location.query.get(id)

    if location is None:
        return HTTPResponse.NOT_FOUND
    else:
        return json.dumps(location.to_dict()), 200

# get one geolocation
@admin.get('/api/geolocation/<int:id>')
def api_geolocation_get(id):
    """
    Endpoint to get a single geolocation
    :param id: id of the geolocation
    :return: geolocation in json format / success or error
    """
    geolocation = GeoLocation.query.get(id)

    if geolocation is None:
        return HTTPResponse.NOT_FOUND
    else:
        return json.dumps(geolocation.to_dict()), 200

@admin.route('/component-data/', defaults={'id': None})
@roles_required('Admin')
def locations_config(id):
    """Endpoint for locations configurations."""
    return render_template('views/admin/component-data.html')


# location admin level endpoints
@admin.route('/api/location-admin-levels/', methods=['GET', 'POST'])
def api_location_admin_levels():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = LocationAdminLevel.query.filter(
        *query).order_by(-LocationAdminLevel.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/location-admin-level')
@roles_required('Admin')
def api_location_admin_level_create():
    admin_level = LocationAdminLevel()
    admin_level.from_json(request.json['item'])

    if admin_level.save():
        return F'Item created successfully ID ${admin_level.id} !', 200
    else:
        return 'Creation failed.', 417


@admin.put('/api/location-admin-level/<int:id>')
@roles_required('Admin')
def api_location_admin_level_update(id):
    admin_level = LocationAdminLevel.query.get(id)
    if admin_level:
        admin_level.from_json(request.json.get('item'))
        if admin_level.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND


# location type endpoints
@admin.route('/api/location-types/', methods=['GET', 'POST'])
def api_location_types():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = LocationType.query.filter(
        *query).order_by(-LocationType.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/location-type')
@roles_required('Admin')
def api_location_type_create():
    location_type = LocationType()
    location_type.from_json(request.json['item'])

    if location_type.save():
        return F'Item created successfully ID ${location_type.id} !', 200
    else:
        return 'Creation failed.', 417


@admin.put('/api/location-type/<int:id>')
@roles_required('Admin')
def api_location_type_update(id):
    location_type = LocationType.query.get(id)

    if location_type:
        location_type.from_json(request.json.get('item'))
        if location_type.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND


@admin.delete('/api/location-type/<int:id>')
@roles_required('Admin')
def api_location_type_delete(id):
    """
    Endpoint to delete a location type
    :param id: id of the location type to be deleted
    :return: success/error
    """
    location_type = LocationType.query.get(id)
    if location_type.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, location_type.to_mini(), 'location_type')
        return F'Location Type Deleted #{location_type.id}', 200
    else:
        return 'Error deleting location type', 417


@admin.route('/api/countries/', methods=['GET', 'POST'])
def api_countries():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    q = request.args.get('q')
    if q:
        result = Country.query.filter(or_(
                    Country.title.ilike(f'%{q}%'), 
                    Country.title_tr.ilike(f'%{q}%'))).order_by(-Country.id).paginate(page=page, per_page=per_page, count=True)
    else:
        result = Country.query.order_by(-Country.id).paginate(page=page, per_page=per_page, count=True)

    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/country')
@roles_required('Admin')
def api_country_create():
    country = Country()
    country.from_json(request.json['item'])

    if country.save():
        return F'Item created successfully ID ${country.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/country/<int:id>')
@roles_required('Admin')
def api_country_update(id):
    country = Country.query.get(id)

    if country:
        country.from_json(request.json.get('item'))
        if country.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/country/<int:id>')
@roles_required('Admin')
def api_country_delete(id):
    """
    Endpoint to delete a country
    :param id: id of the country to be deleted
    :return: success/error
    """
    country = Country.query.get(id)
    if country.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, country.to_mini(), 'country')
        return F'Country Deleted #{country.id}', 200
    else:
        return 'Error deleting country', 417


@admin.route('/api/ethnographies/', methods=['GET', 'POST'])
def api_ethnographies():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    q = request.args.get('q')
    if q:
        result = Ethnography.query.filter(or_(
                    Ethnography.title.ilike(f'%{q}%'), 
                    Ethnography.title_tr.ilike(f'%{q}%'))).order_by(-Ethnography.id).paginate(page=page, per_page=per_page, count=True)
    else:
        result = Ethnography.query.order_by(-Ethnography.id).paginate(page=page, per_page=per_page, count=True)

    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/ethnography')
@roles_required('Admin')
def api_ethnography_create():
    ethnography = Ethnography()
    ethnography.from_json(request.json['item'])

    if ethnography.save():
        return F'Item created successfully ID ${ethnography.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/ethnography/<int:id>')
@roles_required('Admin')
def api_ethnography_update(id):
    ethnography = Ethnography.query.get(id)

    if ethnography:
        ethnography.from_json(request.json.get('item'))
        if ethnography.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/ethnography/<int:id>')
@roles_required('Admin')
def api_ethnography_delete(id):
    """
    Endpoint to delete an ethnography
    :param id: id of the ethnography to be deleted
    :return: success/error
    """
    ethnography = Ethnography.query.get(id)
    if ethnography.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, ethnography.to_mini(), 'ethnography')
        return F'Ethnography Deleted #{ethnography.id}', 200
    else:
        return 'Error deleting ethnography', 417


@admin.route('/api/atoainfos/', methods=['GET', 'POST'])
def api_atoainfos():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = AtoaInfo.query.filter(
        *query).order_by(-AtoaInfo.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/atoainfo')
@roles_required('Admin')
def api_atoainfo_create():
    atoainfo = AtoaInfo()
    atoainfo.from_json(request.json['item'])

    if not (atoainfo.title and atoainfo.reverse_title):
        return 'Title and Reverse Title are required.', 417

    if atoainfo.save():
        return F'Item created successfully ID ${atoainfo.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/atoainfo/<int:id>')
@roles_required('Admin')
def api_atoainfo_update(id):
    atoainfo = AtoaInfo.query.get(id)

    if atoainfo:
        atoainfo.from_json(request.json.get('item'))
        if atoainfo.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/atoainfo/<int:id>')
@roles_required('Admin')
def api_atoainfo_delete(id):
    """
    Endpoint to delete an AtoaInfo
    :param id: id of the AtoaInfo to be deleted
    :return: success/error
    """
    atoainfo = AtoaInfo.query.get(id)
    if atoainfo.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, atoainfo.to_mini(), 'atoainfo')
        return F'AtoaInfo Deleted #{atoainfo.id}', 200
    else:
        return 'Error deleting AtoaInfo', 417


@admin.route('/api/atobinfos/', methods=['GET', 'POST'])
def api_atobinfos():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = AtobInfo.query.filter(
        *query).order_by(-AtobInfo.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/atobinfo')
@roles_required('Admin')
def api_atobinfo_create():
    atobinfo = AtobInfo()
    atobinfo.from_json(request.json['item'])

    if atobinfo.save():
        return F'Item created successfully ID ${atobinfo.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/atobinfo/<int:id>')
@roles_required('Admin')
def api_atobinfo_update(id):
    atobinfo = AtobInfo.query.get(id)

    if atobinfo:
        atobinfo.from_json(request.json.get('item'))
        if atobinfo.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/atobinfo/<int:id>')
@roles_required('Admin')
def api_atobinfo_delete(id):
    """
    Endpoint to delete an AtobInfo
    :param id: id of the AtobInfo to be deleted
    :return: success/error
    """
    atobinfo = AtobInfo.query.get(id)
    if atobinfo.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, atobinfo.to_mini(), 'atobinfo')
        return F'AtobInfo Deleted #{atobinfo.id}', 200
    else:
        return 'Error deleting AtobInfo', 417


@admin.route('/api/btobinfos/', methods=['GET', 'POST'])
def api_btobinfos():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = BtobInfo.query.filter(
        *query).order_by(-BtobInfo.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/btobinfo')
@roles_required('Admin')
def api_btobinfo_create():
    btobinfo = BtobInfo()
    btobinfo.from_json(request.json['item'])

    if btobinfo.save():
        return F'Item created successfully ID ${btobinfo.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/btobinfo/<int:id>')
@roles_required('Admin')
def api_btobinfo_update(id):
    btobinfo = BtobInfo.query.get(id)

    if btobinfo:
        btobinfo.from_json(request.json.get('item'))
        if btobinfo.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/btobinfo/<int:id>')
@roles_required('Admin')
def api_btobinfo_delete(id):
    """
    Endpoint to delete a BtobInfo
    :param id: id of the BtobInfo to be deleted
    :return: success/error
    """
    btobinfo = BtobInfo.query.get(id)
    if btobinfo.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, btobinfo.to_mini(), 'btobinfo')
        return F'BtobInfo Deleted #{btobinfo.id}', 200
    else:
        return 'Error deleting BtobInfo', 417


@admin.route('/api/itoainfos/', methods=['GET', 'POST'])
def api_itoainfos():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = ItoaInfo.query.filter(
        *query).order_by(-ItoaInfo.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/itoainfo')
@roles_required('Admin')
def api_itoainfo_create():
    itoainfo = ItoaInfo()
    itoainfo.from_json(request.json['item'])

    if itoainfo.save():
        return F'Item created successfully ID ${itoainfo.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/itoainfo/<int:id>')
@roles_required('Admin')
def api_itoainfo_update(id):
    itoainfo = ItoaInfo.query.get(id)

    if itoainfo:
        itoainfo.from_json(request.json.get('item'))
        if itoainfo.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/itoainfo/<int:id>')
@roles_required('Admin')
def api_itoainfo_delete(id):
    """
    Endpoint to delete an ItoaInfo
    :param id: id of the ItoaInfo to be deleted
    :return: success/error
    """
    itoainfo = ItoaInfo.query.get(id)
    if itoainfo.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, itoainfo.to_mini(), 'itoainfo')
        return F'ItoaInfo Deleted #{itoainfo.id}', 200
    else:
        return 'Error deleting ItoaInfo', 417

@admin.route('/api/itobinfos/', methods=['GET', 'POST'])
def api_itobinfos():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = ItobInfo.query.filter(
        *query).order_by(-ItobInfo.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/itobinfo')
@roles_required('Admin')
def api_itobinfo_create():
    itobinfo = ItobInfo()
    itobinfo.from_json(request.json['item'])

    if itobinfo.save():
        return F'Item created successfully ID ${itobinfo.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/itobinfo/<int:id>')
@roles_required('Admin')
def api_itobinfo_update(id):
    itobinfo = ItobInfo.query.get(id)

    if itobinfo:
        itobinfo.from_json(request.json.get('item'))
        if itobinfo.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/itobinfo/<int:id>')
@roles_required('Admin')
def api_itobinfo_delete(id):
    """
    Endpoint to delete an ItobInfo
    :param id: id of the ItobInfo to be deleted
    :return: success/error
    """
    itobinfo = ItobInfo.query.get(id)
    if itobinfo.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, itobinfo.to_mini(), 'itobinfo')
        return F'ItobInfo Deleted #{itobinfo.id}', 200
    else:
        return 'Error deleting ItobInfo', 417


@admin.route('/api/itoiinfos/', methods=['GET', 'POST'])
def api_itoiinfos():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = ItoiInfo.query.filter(
        *query).order_by(-ItoiInfo.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/itoiinfo')
@roles_required('Admin')
def api_itoiinfo_create():
    itoiinfo = ItoiInfo()
    itoiinfo.from_json(request.json['item'])

    if itoiinfo.save():
        return F'Item created successfully ID ${itoiinfo.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/itoiinfo/<int:id>')
@roles_required('Admin')
def api_itoiinfo_update(id):
    itoiinfo = ItoiInfo.query.get(id)

    if itoiinfo:
        itoiinfo.from_json(request.json.get('item'))
        if itoiinfo.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/itoiinfo/<int:id>')
@roles_required('Admin')
def api_itoiinfo_delete(id):
    """
    Endpoint to delete an ItoiInfo
    :param id: id of the ItoiInfo to be deleted
    :return: success/error
    """
    itoiinfo = ItoiInfo.query.get(id)
    if itoiinfo.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, itoiinfo.to_mini(), 'itoiinfo')
        return F'ItoiInfo Deleted #{itoiinfo.id}', 200
    else:
        return 'Error deleting ItoiInfo', 417


@admin.route('/api/mediacategories/', methods=['GET', 'POST'])
def api_mediacategories():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = MediaCategory.query.filter(
        *query).order_by(-MediaCategory.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/mediacategory')
@roles_required('Admin')
def api_mediacategory_create():
    mediacategory = MediaCategory()
    mediacategory.from_json(request.json['item'])

    if mediacategory.save():
        return f'Item created successfully ID {mediacategory.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/mediacategory/<int:id>')
@roles_required('Admin')
def api_mediacategory_update(id):
    mediacategory = MediaCategory.query.get(id)

    if mediacategory:
        mediacategory.from_json(request.json.get('item'))
        if mediacategory.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/mediacategory/<int:id>')
@roles_required('Admin')
def api_mediacategory_delete(id):
    """
    Endpoint to delete a MediaCategory
    :param id: id of the MediaCategory to be deleted
    :return: success/error
    """
    mediacategory = MediaCategory.query.get(id)
    if mediacategory.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, mediacategory.to_mini(), 'mediacategory')
        return f'MediaCategory Deleted #{mediacategory.id}', 200
    else:
        return 'Error deleting MediaCategory', 417

@admin.route('/api/geolocationtypes/', methods=['GET', 'POST'])
def api_geolocationtypes():
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = GeoLocationType.query.filter(
        *query).order_by(-GeoLocationType.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/geolocationtype')
@roles_required('Admin')
def api_geolocationtype_create():
    geolocationtype = GeoLocationType()
    geolocationtype.from_json(request.json['item'])

    if geolocationtype.save():
        return f'Item created successfully ID {geolocationtype.id} !', 200
    else:
        return 'Creation failed.', 417

@admin.put('/api/geolocationtype/<int:id>')
@roles_required('Admin')
def api_geolocationtype_update(id):
    geolocationtype = GeoLocationType.query.get(id)

    if geolocationtype:
        geolocationtype.from_json(request.json.get('item'))
        if geolocationtype.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/geolocationtype/<int:id>')
@roles_required('Admin')
def api_geolocationtype_delete(id):
    """
    Endpoint to delete a GeoLocationType
    :param id: id of the GeoLocationType to be deleted
    :return: success/error
    """
    geolocationtype = GeoLocationType.query.get(id)
    if geolocationtype.delete():
        # Record Activity
        Activity.create(current_user, Activity.ACTION_DELETE, geolocationtype.to_mini(), 'geolocationtype')
        return f'GeoLocationType Deleted #{geolocationtype.id}', 200
    else:
        return 'Error deleting GeoLocationType', 417



# Bulletin routes
@admin.route('/primary-records/', defaults={'id': None})
@admin.route('/primary-records/<int:id>')
def bulletins(id):
    """Endpoint for bulletins management."""
    # Pass relationship information
    atobInfo = [item.to_dict() for item in AtobInfo.query.all()]
    btobInfo = [item.to_dict() for item in BtobInfo.query.all()]
    atoaInfo = [item.to_dict() for item in AtoaInfo.query.all()]
    itobInfo = [item.to_dict() for item in ItobInfo.query.all()]
    itoaInfo = [item.to_dict() for item in ItoaInfo.query.all()]
    itoiInfo = [item.to_dict() for item in ItoiInfo.query.all()]
    otooInfo = [item.to_dict() for item in OtooInfo.query.all()]
    otobInfo = [item.to_dict() for item in OtobInfo.query.all()]
    otoiInfo = [item.to_dict() for item in OtoiInfo.query.all()]
    otoaInfo = [item.to_dict() for item in OtoaInfo.query.all()]
    statuses = [item.to_dict() for item in WorkflowStatus.query.all()]
    return render_template('views/admin/bulletins.html',
                           atoaInfo=atoaInfo,
                           itoaInfo=itoaInfo,
                           itoiInfo=itoiInfo,
                           atobInfo=atobInfo,
                           btobInfo=btobInfo,
                           itobInfo=itobInfo,
                           otobInfo=otobInfo,
                           otooInfo=otooInfo,
                           otoiInfo=otoiInfo,
                           otoaInfo=otoaInfo,
                           statuses=statuses)


def make_cache_key(*args, **kwargs):
    json_key = str(hash(str(request.json)))
    args_key = request.args.get('page') + request.args.get('per_page', PER_PAGE) + request.args.get('cache', '')
    return json_key + args_key


@admin.route('/api/bulletins/', methods=['POST', 'GET'])
@cache.cached(15, make_cache_key)
def api_bulletins():
    """Returns bulletins in JSON format, allows search and paging."""
    su = SearchUtils(request.json, cls='Bulletin')
    queries, ops = su.get_query()
    result = Bulletin.query.filter(or_(Bulletin.deleted == False, Bulletin.deleted.is_(None))).filter(*queries.pop(0))

    # nested queries
    if len(queries) > 0:
        while queries:
            nextOp = ops.pop(0)
            nextQuery = queries.pop(0)
            if nextOp == 'union':
                result = result.union(Bulletin.query.filter(*nextQuery))
            elif nextOp == 'intersect':
                result = result.intersect(Bulletin.query.filter(*nextQuery))

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'
    elif sort_by == '_status':
        sort_by = 'status'

    #Adjust query for sorting by a field in a related model if needed
    if sort_by == "assigned_to.name":
        result = result.outerjoin(User, Bulletin.assigned_to_id == User.id)
        result = result.order_by(User.name.desc() if sort_desc else User.name)
    elif sort_by == 'roles':
        #bulletins to Roles is a many-many relationship so get association table then sort
        role_alias = aliased(Role)
        result = result.outerjoin(role_alias, Bulletin.roles)
        result = result.order_by(role_alias.name.desc() if sort_desc else role_alias.name)
    else:
        if hasattr(Bulletin, sort_by):
            result = result.order_by(getattr(Bulletin, sort_by).desc() if sort_desc else getattr(Bulletin, sort_by))
        else:
            return {'error': 'Invalid sort_by fied'}, 400

    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)
    result = result.order_by(Bulletin.id.desc()).paginate(page=page, per_page=per_page, count=True)

    # Select json encoding type
    mode = request.args.get('mode', '1')
    response = {'items': [item.to_dict(mode=mode) for item in result.items], 'perPage': per_page, 'total': result.total}

    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/bulletin/')
@roles_accepted('Admin', 'DA')
def api_bulletin_create():
    """Creates a new bulletin."""
    bulletin = Bulletin()
    # assign automatically to the creator user
    bulletin.assigned_to_id = current_user.id
    # assignment will be overwritten if it is specified in the creation request
    bulletin.from_json(request.json['item'])
    bulletin.save(True)

    # the below will create the first revision by default
    bulletin.create_revision()
    # Record activity
    Activity.create(current_user, Activity.ACTION_CREATE, bulletin.to_mini(), 'bulletin')
    return F'Created Bulletin #{bulletin.id}', 200


@admin.put('/api/bulletin/<int:id>')
@roles_accepted('Admin', 'DA')
def api_bulletin_update(id):
    """Updates a bulletin."""
    bulletin = Bulletin.query.get(id)
    if bulletin is not None:
        if not current_user.can_access(bulletin):
            return 'Restricted Access', 403
        bulletin = bulletin.from_json(request.json['item'])
        bulletin.create_revision()
        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, bulletin.to_mini(), 'bulletin')
        return F'Saved Bulletin #{bulletin.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/bulletin/<int:id>')
@roles_required('Admin')
def api_bulletin_delete(id):
    """
    Endpoint to delete a bulletin
    :param id: id of the bulletin to delete
    :return: success/error based on operation's result
    """
    bulletin = Bulletin.query.get(id)
    if bulletin is None:
        return HTTPResponse.NOT_FOUND
    # Record Activity
    Activity.create(current_user, Activity.ACTION_DELETE, bulletin.to_mini(), 'bulletin')
    bulletin.deleted = True
    bulletin.create_revision()
    return F'Deleted Bulletin #{bulletin.id}', 200


# Add/Update review bulletin endpoint
@admin.put('/api/bulletin/review/<int:id>')
@roles_accepted('Admin', 'DA')
def api_bulletin_review_update(id):
    """
    Endpoint to update a bulletin review
    :param id: id of the bulletin
    :return: success/error based on the outcome
    """
    bulletin = Bulletin.query.get(id)
    if bulletin is not None:
        if not current_user.can_access(bulletin):
            return 'Restricted Access', 403

        bulletin.review = request.json['item']['review'] if 'review' in request.json['item'] else ''
        bulletin.review_action = request.json['item']['review_action'] if 'review_action' in request.json[
            'item'] else ''

        if bulletin.status == 'Peer Review Assigned':
            bulletin.comments = 'Added Peer Review'
        if bulletin.status == 'Peer Reviewed':
            bulletin.comments = 'Updated Peer Review'

        bulletin.status = 'Peer Reviewed'

        # append refs
        refs = request.json.get('item', {}).get('revrefs', [])

        bulletin.ref = bulletin.ref + refs

        if bulletin.save():
            # Create a revision using latest values
            # this method automatically commits
            #  bulletin changes (referenced)           
            bulletin.create_revision()

            # Record Activity
            Activity.create(current_user, Activity.ACTION_UPDATE, bulletin.to_mini(), 'bulletin')
            return F'Bulletin review updated #{bulletin.id}', 200
        else:
            return F'Error saving Bulletin #{id}', 417
    else:
        return HTTPResponse.NOT_FOUND


# bulk update bulletin endpoint
@admin.put('/api/bulletin/bulk/')
@roles_accepted('Admin', 'Mod')
def api_bulletin_bulk_update():
    """
    Endpoint to bulk update bulletins
    :return: success / error
    """

    ids = request.json['items']
    bulk = request.json['bulk']

    # non-intrusive hard validation for access roles based on user
    if not current_user.has_role('Admin') and not current_user.has_role('Mod'):
        # silently discard access roles
        bulk.pop('roles', None)

    if ids and len(bulk):
        job = bulk_update_bulletins.delay(ids, bulk, current_user.id)
        # store job id in user's session for status monitoring
        key = F'user{current_user.id}:{job.id}'
        rds.set(key, job.id)
        # expire in 3 hours
        rds.expire(key, 60 * 60 * 3)
        return 'Bulk update queued successfully', 200
    else:
        return 'No items selected, or nothing to update', 417


# get one bulletin
@admin.get('/api/bulletin/<int:id>')
def api_bulletin_get(id):
    """
    Endpoint to get a single bulletin
    :param id: id of the bulletin
    :return: bulletin in json format / success or error
    """
    bulletin = Bulletin.query.get(id)
    mode = request.args.get('mode', None)
    if not bulletin:
        return 'Not found', 404
    else:
        # hide review from view-only users
        if not current_user.roles:
            bulletin.review = None
        if current_user.can_access(bulletin):
            return json.dumps(bulletin.to_dict(mode)), 200
        else:
            # block access altogether here, doesn't make sense to send only the id
            return 'Restricted Access', 403


# get bulletin relations
@admin.get('/api/bulletin/relations/<int:id>')
def bulletin_relations(id):
    """
    Endpoint to return related entities of a bulletin
    :return:
    """
    cls = request.args.get('class', None)
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', REL_PER_PAGE, int)
    if not cls or cls not in relation_classes:
        return HTTPResponse.NOT_FOUND
    bulletin = Bulletin.query.get(id)
    if not bulletin:
        return HTTPResponse.NOT_FOUND
    items = []

    if cls == 'bulletin':
        items = bulletin.bulletin_relations
    elif cls == 'actor':
        items = bulletin.actor_relations
    elif cls == 'incident':
        items = bulletin.incident_relations
    elif cls == 'organization':
        items = bulletin.organization_relations

    start = (page - 1) * per_page
    end = start + per_page
    data = items[start:end]

    load_more = False if end >= len(items) else True
    if data:
        if cls == 'bulletin':
            data = [item.to_dict(exclude=bulletin) for item in data]
        else:
            data = [item.to_dict() for item in data]

    return json.dumps({'items': data, 'more': load_more}), 200


@admin.route('/api/bulletin/import/', methods=['POST'])
@roles_required('Admin')
def api_bulletin_import():
    """
    Endpoint to import bulletins from csv data
    :return: success / error
    """
    if 'csv' in request.files:
        Bulletin.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400


# ----- self assign endpoints -----

@admin.route('/api/bulletin/assignother/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_bulletin_assign(id):
    """assign a bulletin to another user"""
    bulletin = Bulletin.query.get(id)

    if not current_user.can_access(bulletin):
        return 'Restricted Access', 403
    
    if bulletin:
        b = request.json.get('bulletin')
        if not b or not b.get('assigned_to_id'):
            return 'No user selected',  400
        # update bulletin assignement
        bulletin.assigned_to_id = b.get('assigned_to_id')
        bulletin.comments = b.get('comments', '')
        bulletin.ref = bulletin.ref or []
        bulletin.ref = bulletin.ref + b.get('ref', [])

        # Change status to assigned if needed
        if bulletin.status == 'Machine Created' or bulletin.status == 'Human Created':
            bulletin.status = 'Assigned'

        # Create a revision using latest values
        # this method automatically commits
        # bulletin changes (referenced)
        bulletin.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, bulletin.to_mini(), 'bulletin')
        return F'Saved Bulletin #{bulletin.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/bulletin/assign/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_bulletin_self_assign(id):
    """assign a bulletin to the user"""

    # permission check
    if not current_user.can_self_assign:
        return 'User not allowed to self assign', 400

    bulletin = Bulletin.query.get(id)

    if not current_user.can_access(bulletin):
        return 'Restricted Access', 403

    if bulletin:
        b = request.json.get('bulletin')
        # workflow check
        if bulletin.assigned_to_id and bulletin.assigned_to.active:
            return 'Item already assigned to an active user', 400

        # update bulletin assignement
        bulletin.assigned_to_id = current_user.id
        bulletin.comments = b.get('comments')
        bulletin.ref = bulletin.ref or []
        bulletin.ref = bulletin.ref + b.get('ref', [])

        # Change status to assigned if needed
        if bulletin.status == 'Machine Created' or bulletin.status == 'Human Created':
            bulletin.status = 'Assigned'

        # Create a revision using latest values
        # this method automatically commits
        # bulletin changes (referenced)
        bulletin.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, bulletin.to_mini(), 'bulletin')
        return F'Saved Bulletin #{bulletin.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/actor/assignother/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_actor_assign(id):
    """assign a actor to another user"""
    actor = Actor.query.get(id)

    if not current_user.can_access(actor):
        return 'Restricted Access', 403

    if actor:
        a = request.json.get('actor')
        if not a or not a.get('assigned_to_id'):
            return 'No user selected',  400
        # update actor assignement
        actor.assigned_to_id = a.get('assigned_to_id')
        actor.comments = a.get('comments', '')

        # Change status to assigned if needed
        if actor.status == 'Machine Created' or actor.status == 'Human Created':
            actor.status = 'Assigned'

        # Create a revision using latest values
        # this method automatically commits
        # actor changes (referenced)
        actor.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, actor.to_mini(), 'actor')
        return F'Saved Actor #{actor.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/actor/assign/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_actor_self_assign(id):
    """ self assign an actor to the user"""

    # permission check
    if not current_user.can_self_assign:
        return 'User not allowed to self assign', 400

    actor = Actor.query.get(id)

    if not current_user.can_access(actor):
        return 'Restricted Access', 403

    if actor:
        a = request.json.get('actor')
        # workflow check
        if actor.assigned_to_id and actor.assigned_to.active:
            return 'Item already assigned to an active user', 400

        # update bulletin assignement
        actor.assigned_to_id = current_user.id
        actor.comments = a.get('comments')

        # Change status to assigned if needed
        if actor.status == 'Machine Created' or actor.status == 'Human Created':
            actor.status = 'Assigned'

        actor.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, actor.to_mini(), 'actor')
        return F'Saved Actor #{actor.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/incident/assignother/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_incident_assign(id):
    """assign a actor to another user"""
    incident = Incident.query.get(id)

    if not current_user.can_access(incident):
        return 'Restricted Access', 403

    if incident:
        i = request.json.get('incident')
        if not i or not i.get('assigned_to_id'):
            return 'No user selected',  400
        # update incident assignement
        incident.assigned_to_id = i.get('assigned_to_id')
        incident.comments = i.get('comments', '')

        # Change status to assigned if needed
        if incident.status == 'Machine Created' or incident.status == 'Human Created':
            incident.status = 'Assigned'

        # Create a revision using latest values
        # this method automatically commits
        # incident changes (referenced)
        incident.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, incident.to_mini(), 'incident')
        return F'Saved Investigation #{incident.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/incident/assign/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_incident_self_assign(id):
    """ self assign an incident to the user"""

    # permission check
    if not current_user.can_self_assign:
        return 'User not allowed to self assign', 400

    incident = Incident.query.get(id)

    if not current_user.can_access(incident):
        return 'Restricted Access', 403

    if incident:
        i = request.json.get('incident')
        # workflow check
        if incident.assigned_to_id and incident.assigned_to.active:
            return 'Item already assigned to an active user', 400

        # update bulletin assignement
        incident.assigned_to_id = current_user.id
        incident.comments = i.get('comments')

        # Change status to assigned if needed
        if incident.status == 'Machine Created' or incident.status == 'Human Created':
            incident.status = 'Assigned'

        incident.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, incident.to_mini(), 'incident')
        return F'Saved Investigation #{incident.id}', 200
    else:
        return HTTPResponse.NOT_FOUND


# Media special endpoints

@admin.post('/api/shapefile/chunk')
@roles_accepted('Admin', 'DA')
def api_shapefile_chunk():
    file = request.files["file"]

    if not Media.validate_shapefile_extension(file.filename):
        return 'This file type is not allowed', 415

    dz_uuid = request.form.get("dzuuid")
    shapefile_group_uuid = request.form.get("shapefile_group_uuid")
    title = request.form["title"]
    if not dz_uuid or not shapefile_group_uuid or not file.filename or not title:
        return 'Invalid Request', 425

    # Chunked upload
    try:
        current_chunk = int(request.form["dzchunkindex"])
        total_chunks = int(request.form["dztotalchunkcount"])
        total_size = int(request.form["dztotalfilesize"])
    except KeyError as err:
        raise abort(400, body=f"Not all required fields supplied, missing {err}")
    except ValueError:
        raise abort(400, body=f"Values provided were not in expected format")
    
    if not safe_join(str(Media.media_file), dz_uuid):
        return 'Invalid Request', 425

    save_dir = Media.shapefile_dir / shapefile_group_uuid / secure_filename(dz_uuid)

    filename = Media.standardize_shapefile_filename(file.filename, title)
    filepath = (Media.shapefile_dir / shapefile_group_uuid / filename)

    # validate current chunk
    if not safe_join(str(save_dir), str(current_chunk)) or current_chunk.__class__ != int:
        return 'Invalid Request', 425

    if not save_dir.exists():
        save_dir.mkdir(exist_ok=True, parents=True)

    # Save the individual chunk
    with open(save_dir / secure_filename(str(current_chunk)), "wb") as f:
        file.save(f)

    # See if we have all the chunks downloaded
    completed = current_chunk == total_chunks - 1

    if completed:
        with open(filepath, "wb") as f:
            for file_number in range(total_chunks):
                f.write((save_dir / str(file_number)).read_bytes())
        shutil.rmtree(save_dir)
        total_files = request.form["numFiles"]
        current_file_index = request.form["currentFileNumber"]

        if current_file_index == total_files:
            geojson_path = Media.create_geojson_from_shapefiles(shapefile_group_uuid, title)
            response = { 
                'filename': str(geojson_path),
                'shapefile_group_uuid': shapefile_group_uuid,
                'completed': True,
                'title': title
            }
            return Response(json.dumps(response)), 200

        response = {'filename': str(filename)}
        return Response(json.dumps(response), content_type='application/json'), 200

    return "Chunk uploaded successfully", 200

@admin.get('/api/media/shapefile/download/<shapefile_group_uuid>')
@roles_accepted('Admin', 'DA')
def api_shapefile_download(shapefile_group_uuid):
    """
    Endpoint to download a shapefile group
    :param shapefile_group_uuid: uuid of the shapefile group
    :return: file download
    """
    shapefile_group = Media.shapefile_dir / shapefile_group_uuid
    if not shapefile_group.exists():
        return 'Not found', 404
    zip_dir = Media.shapefile_dir / shapefile_group_uuid
    # check if zip file already exists in directory called shapefiles.zip
    for file in zip_dir.iterdir():
        if file.is_file() and file.suffix == '.zip':
            return send_from_directory(f'media/shapefiles/{shapefile_group_uuid}', file.name)
    zip_filename = Media.create_shapefile_zip(shapefile_group_uuid)
    return send_from_directory(f'media/shapefiles/{shapefile_group_uuid}', zip_filename, as_attachment=True)

@admin.post('/api/media/chunk')
@roles_accepted('Admin', 'DA')
def api_medias_chunk():
    file = request.files['file']

    # we can immediately validate the file type here
    if not Media.validate_media_extension(file.filename):
        return 'This file type is not allowed', 415
    filename = Media.generate_file_name(file.filename)
    filepath = (Media.media_dir / filename).as_posix()

    dz_uuid = request.form.get("dzuuid")
    if not dz_uuid:
        # Assume this file has not been chunked
        with open(f"{filepath}", "wb") as f:
            file.save(f)

        # get sha256 hash
        f = open(filepath, 'rb').read()
        etag = hashlib.sha256(f).hexdigest()
        
        response = {'etag': etag, 'filename': filename}
        return Response(json.dumps(response), content_type='application/json'), 200

    # Chunked upload
    try:
        current_chunk = int(request.form["dzchunkindex"])
        total_chunks = int(request.form["dztotalchunkcount"])
        total_size = int(request.form["dztotalfilesize"])
    except KeyError as err:
        raise abort(400, body=f"Not all required fields supplied, missing {err}")
    except ValueError:
        raise abort(400, body=f"Values provided were not in expected format")

    # validate dz_uuid
    if not safe_join(str(Media.media_file), dz_uuid):
        return 'Invalid Request', 425

    save_dir = Media.media_dir / secure_filename(dz_uuid)

    # validate current chunk
    if not safe_join(str(save_dir), str(current_chunk)) or current_chunk.__class__ != int:
        return 'Invalid Request', 425

    if not save_dir.exists():
        save_dir.mkdir(exist_ok=True, parents=True)

    # Save the individual chunk
    with open(save_dir / secure_filename(str(current_chunk)), "wb") as f:
        file.save(f)

    # See if we have all the chunks downloaded
    completed = current_chunk == total_chunks - 1

    # Concat all the files into the final file when all are downloaded
    if completed:
        with open(filepath, "wb") as f:
            for file_number in range(total_chunks):
                f.write((save_dir / str(file_number)).read_bytes())

        if os.stat(filepath).st_size != total_size:
            raise abort(400, description=f"Error uploading the file")

        print(f"{file.filename} has been uploaded")
        shutil.rmtree(save_dir)
        # get sha256 hash
        f = open(filepath, 'rb').read()
        etag = hashlib.sha256(f).hexdigest()

        # validate etag here // if it exists // reject the upload and send an error code
        if Media.query.filter(Media.etag == etag).first():
            return 'Error, file already exists', 409

        if not current_app.config.get('FILESYSTEM_LOCAL') and not 'etl' in request.referrer:
            print('uploading file to s3 :::>')
            s3 = boto3.resource('s3')
            s3.Bucket(current_app.config['S3_BUCKET']).upload_file(filepath, filename)
            # Clean up file if s3 mode is selected
            try:
                os.remove(filepath)
            except Exception as e:
                print(e)

        response = {'etag': etag, 'filename': filename}
        return Response(json.dumps(response), content_type='application/json'), 200

    return "Chunk upload successful", 200


@admin.route('/api/media/upload/', methods=['POST'])
@roles_accepted('Admin', 'DA')
def api_medias_upload():
    """
    Endpoint to upload files (based on file system settings : s3 or local file system)
    :return: success /error based on operation's result
    """
    file = request.files.get('file')
    if file:
        if current_app.config['FILESYSTEM_LOCAL'] or (
                'etl' in request.referrer and not current_app.config['FILESYSTEM_LOCAL']):
            return api_local_medias_upload(request)
        else:

            s3 = boto3.resource('s3', aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
                                aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY'])

            # final file
            filename = Media.generate_file_name(file.filename)
            # filepath = (Media.media_dir/filename).as_posix()

            response = s3.Bucket(current_app.config['S3_BUCKET']).put_object(Key=filename, Body=file)
            # print(response.get())
            etag = response.get()['ETag'].replace('"', '')

            # check if file already exists
            if Media.query.filter(Media.etag == etag).first():
                return 'Error: File already exists', 409

            return json.dumps({'filename': filename, 'etag': etag}), 200

    return 'Invalid request params', 417



GRACE_PERIOD = timedelta(hours=2)  # 2 hours
S3_URL_EXPIRY = 3600 # 2 hours
# return signed url from s3 valid for some time
@admin.route('/api/media/<filename>')
def serve_media(filename):
    """
    Endpoint to generate file urls to be served (based on file system type)
    :param filename: name of the file
    :return: temporarily accessible url of the file
    """

    if current_app.config['FILESYSTEM_LOCAL']:
        file_path = safe_join('/admin/api/serve/media', filename)
        if file_path:
            return file_path, 200
        else:
            return 'Invalid Request', 425
    else:
        # validate access control
        media = Media.query.filter(Media.media_file == filename).first()

        s3 = boto3.client('s3',
                          aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
                          aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY'],
                          region_name=current_app.config['AWS_REGION']
                          )

        # allow generation of s3 urls for a short period while the media is not created
        if media is None:
            # this means the file is not in the database
            # we allow serving it briefly while the user is still creating the media
            try:
                # Get the last modified time of the file
                resp = s3.head_object(Bucket=current_app.config['S3_BUCKET'], Key=filename)
                last_modified = resp['LastModified']

                # Check if file is uploaded within the grace period
                if datetime.utcnow() - last_modified.replace(tzinfo=None) <= GRACE_PERIOD:
                    params = {'Bucket': current_app.config['S3_BUCKET'], 'Key': filename}
                    url = s3.generate_presigned_url('get_object', Params=params, ExpiresIn=36000)
                    return url, 200
                else:
                    return HTTPResponse.FORBIDDEN
            except s3.exceptions.NoSuchKey:
                return HTTPResponse.NOT_FOUND
            except Exception as e:
                return HTTPResponse.INTERNAL_SERVER_ERROR
        else:
            # media exists in the database, check access control restrictions
            if not current_user.can_access(media):
                return 'Restricted Access', 403

            params = {'Bucket': current_app.config['S3_BUCKET'], 'Key': filename}
            if filename.lower().endswith('pdf'):
                params['ResponseContentType'] = 'application/pdf'

            return s3.generate_presigned_url('get_object', Params=params, ExpiresIn=S3_URL_EXPIRY)


def api_local_medias_upload(request):
    # file pond sends multiple requests for multiple files (handle each request as a separate file )
    try:
        file = request.files.get('file')
        # final file
        filename = Media.generate_file_name(file.filename)
        filepath = (Media.media_dir / filename).as_posix()
        file.save(filepath)
        # get sha256 hash
        f = open(filepath, 'rb').read()
        etag = hashlib.sha256(f).hexdigest()
        # check if file already exists
        if Media.query.filter(Media.etag == etag).first():
            return 'Error: File already exists', 409

        response = {'etag': etag, 'filename': filename}

        return Response(json.dumps(response), content_type='application/json'), 200
    except Exception as e:
        print(e)
        return F'Request Failed', 417


@admin.route('/api/serve/media/<filename>')
def api_local_serve_media(filename):
    """
    serves file from local file system
    """

    media = Media.query.filter(Media.media_file == filename).first()
    if media and not current_user.can_access(media):
        return 'Restricted Access', 403
    else:
        if filename.lower().endswith('geojson'):
            shapefile_group_uuid = request.args.get('shapefile_group_uuid')
            if not shapefile_group_uuid:
                return 'Invalid Request', 425
            directory = f'media/shapefiles/{shapefile_group_uuid}'
            return send_from_directory(directory, filename)
        return send_from_directory('media', filename)


@admin.post('/api/inline/upload')
def api_inline_medias_upload():
    try:
        f = request.files.get('file')

        # final file
        filename = Media.generate_file_name(f.filename)
        filepath = (Media.inline_dir / filename).as_posix()
        f.save(filepath)
        response = {'location': filename}

        return Response(json.dumps(response), content_type='application/json'), 200
    except Exception as e:
        print(e)
        return F'Request Failed', 417


@admin.route('/api/serve/inline/<filename>')
def api_local_serve_inline_media(filename):
    """
    serves inline media files - only for authenticated users
    """
    return send_from_directory('media/inline', filename)


# Medias routes

@admin.route('/api/media/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_media_update(id):
    """
    Endpoint to update a media item
    :param id: id of the item to be updated
    :return: success / error
    """
    if request.method == 'PUT':
        media = Media.query.get(id)
        if media is not None:
            media = media.from_json(request.json['item'])
            media.save()
            return 'Saved!', 200
        else:
            return HTTPResponse.NOT_FOUND

    else:
        return HTTPResponse.FORBIDDEN


# Actor routes
@admin.route('/actors/', defaults={'id': None})
@admin.route('/actors/<int:id>')
def actors(id):
    """Endpoint to render actors page."""
    # Pass relationship information
    atobInfo = [item.to_dict() for item in AtobInfo.query.all()]
    btobInfo = [item.to_dict() for item in BtobInfo.query.all()]
    atoaInfo = [item.to_dict() for item in AtoaInfo.query.all()]
    itobInfo = [item.to_dict() for item in ItobInfo.query.all()]
    itoaInfo = [item.to_dict() for item in ItoaInfo.query.all()]
    itoiInfo = [item.to_dict() for item in ItoiInfo.query.all()]
    otooInfo = [item.to_dict() for item in OtooInfo.query.all()]
    otobInfo = [item.to_dict() for item in OtobInfo.query.all()]
    otoiInfo = [item.to_dict() for item in OtoiInfo.query.all()]
    otoaInfo = [item.to_dict() for item in OtoaInfo.query.all()]

    statuses = [item.to_dict() for item in WorkflowStatus.query.all()]
    return render_template('views/admin/actors.html',
                           btobInfo=btobInfo,
                           itobInfo=itobInfo,
                           itoiInfo=itoiInfo,
                           atobInfo=atobInfo,
                           atoaInfo=atoaInfo,
                           otobInfo=otobInfo,
                           otooInfo=otooInfo,
                           otoiInfo=otoiInfo,
                           otoaInfo=otoaInfo,
                           itoaInfo=itoaInfo, statuses=statuses)


@admin.route('/api/actors/', methods=['POST', 'GET'])
def api_actors():
    """Returns actors in JSON format, allows search and paging."""
    su = SearchUtils(request.json, cls='Actor')
    queries, ops = su.get_query()
    result = Actor.query.filter(or_(Actor.deleted == False, Actor.deleted.is_(None))).filter(*queries.pop(0))

    # nested queries
    if len(queries) > 0:
        while queries:
            nextOp = ops.pop(0)
            nextQuery = queries.pop(0)
            if nextOp == 'union':
                result = result.union(Actor.query.filter(*nextQuery))
            elif nextOp == 'intersect':
                result = result.intersect(Actor.query.filter(*nextQuery))

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'
    elif sort_by == '_status':
        sort_by = 'status'

    #Adjust query for sorting by a field in a related model if needed
    if sort_by == "assigned_to.name":
        result = result.outerjoin(User, Actor.assigned_to_id == User.id)
        result = result.order_by(User.name.desc() if sort_desc else User.name)
    elif sort_by == 'roles':
        #Actors to Roles is a many-many relationship so get association table then sort
        role_alias = aliased(Role)
        result = result.outerjoin(role_alias, Actor.roles)
        result = result.order_by(role_alias.name.desc() if sort_desc else role_alias.name)
    else:
        if hasattr(Actor, sort_by):
            result = result.order_by(getattr(Actor, sort_by).desc() if sort_desc else getattr(Actor, sort_by))
        else:
            return {'error': 'Invalid sort_by fied'}, 400

    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)
    result = result.paginate(page=page, per_page=per_page, count=True)

    # Select json encoding type
    mode = request.args.get('mode', '1')
    response = {'items': [item.to_dict(mode=mode) for item in result.items], 'perPage': per_page, 'total': result.total}

    return Response(json.dumps(response),
                    content_type='application/json'), 200


# create actor endpoint
@admin.post('/api/actor/')
@roles_accepted('Admin', 'DA')
def api_actor_create():
    """
    Endpoint to create an Actor item
    :return: success/error based on the operation's result
    """
    actor = Actor()
    # assign actor to creator by default
    actor.assigned_to_id = current_user.id
    # assignment will be overwritten if it is specified in the creation request
    try:
        actor.from_json(request.json['item'])
    except Exception as e:
        return f'Error creating actor: {e}', 400
    result = actor.save()
    if result:
        # the below will create the first revision by default
        actor.create_revision()
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, actor.to_mini(), 'actor')
        return F'Created Actor #{actor.id}', 200
    else:
        return 'Error creating actor', 417


# update actor endpoint
@admin.put('/api/actor/<int:id>')
@roles_accepted('Admin', 'DA')
def api_actor_update(id):
    """
    Endpoint to update an Actor item
    :param id: id of the actor to be updated
    :return: success/error
    """
    actor = Actor.query.get(id)
    if actor is not None:
        # check for restrictions
        if not current_user.can_access(actor):
            return 'Restricted Access', 403

        try:
            actor = actor.from_json(request.json['item'])
        except Exception as e:
            return f'Error updating actor: {e}', 400
        # Create a revision using latest values
        # this method automatically commits
        # actor changes (referenced)
        if actor:
            actor.create_revision()
            # Record activity
            Activity.create(current_user, Activity.ACTION_UPDATE, actor.to_mini(), 'actor')
            return F'Saved Actor #{actor.id}', 200
        else:
            return F'Error saving Actor #{id}', 417
    else:
        return HTTPResponse.NOT_FOUND


@admin.delete('/api/actor/<int:id>')
@roles_required('Admin')
def api_actor_delete(id):
    """
    Endpoint to delete an actor
    :param id: id of the actor to delete
    :return: success/error based on operation's result
    """
    actor = Actor.query.get(id)
    if actor is None:
        return HTTPResponse.NOT_FOUND
    # Record Activity
    Activity.create(current_user, Activity.ACTION_DELETE, actor.to_mini(), 'actor')
    actor.deleted = True
    actor.create_revision()
    return F'Deleted Actor #{actor.id}', 200


# Add/Update review actor endpoint
@admin.put('/api/actor/review/<int:id>')
@roles_accepted('Admin', 'DA')
def api_actor_review_update(id):
    """
    Endpoint to update an Actor's review item
    :param id: id of the actor
    :return: success/error
    """
    actor = Actor.query.get(id)
    if actor is not None:
        if not current_user.can_access(actor):
            return 'Restricted Access', 403

        actor.review = request.json['item']['review'] if 'review' in request.json['item'] else ''
        actor.review_action = request.json['item']['review_action'] if 'review_action' in request.json[
            'item'] else ''

        actor.status = 'Peer Reviewed'

        # Create a revision using latest values
        # this method automatically commits
        #  actor changes (referenced)
        if actor.save():
            actor.create_revision()
            # Record activity
            Activity.create(current_user, Activity.ACTION_UPDATE, actor.to_mini(), 'actor')
            return F'Actor review updated #{id}', 200
        else:
            return F'Error saving Actor #{id}\'s Review', 417
    else:
        return HTTPResponse.NOT_FOUND


# bulk update actor endpoint
@admin.put('/api/actor/bulk/')
@roles_accepted('Admin', 'Mod')
def api_actor_bulk_update():
    """
    Endpoint to bulk update actors
    :return: success/error
    """

    ids = request.json['items']
    bulk = request.json['bulk']

    # non-intrusive hard validation for access roles based on user
    if not current_user.has_role('Admin') and not current_user.has_role('Mod'):
        # silently discard access roles
        bulk.pop('roles', None)

    if ids and len(bulk):
        job = bulk_update_actors.delay(ids, bulk, current_user.id)
        # store job id in user's session for status monitoring
        key = F'user{current_user.id}:{job.id}'
        rds.set(key, job.id)
        # expire in 3 hour
        rds.expire(key, 60 * 60 * 3)
        return 'Bulk update queued successfully.', 200
    else:
        return 'No items selected, or nothing to update', 417


# get one actor

@admin.get('/api/actor/<int:id>')
def api_actor_get(id):
    """
    Endpoint to get a single actor
    :param id: id of the actor
    :return: actor data in json format + success or error in case of failure
    """
    actor = Actor.query.get(id)
    if not actor:
        return 'Not found', 404
    else:
        mode = request.args.get('mode', None)
        if current_user.can_access(actor):
            return json.dumps(actor.to_dict(mode)), 200
        else:
            # block access altogether here, doesn't make sense to send only the id
            return 'Restricted Access', 403


# get actor relations
@admin.get('/api/actor/relations/<int:id>')
def actor_relations(id):
    """
    Endpoint to return related entities of an Actor
    :return:
    """
    cls = request.args.get('class', None)
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', REL_PER_PAGE, int)
    if not cls or cls not in relation_classes:
        return HTTPResponse.NOT_FOUND
    actor = Actor.query.get(id)
    if not actor:
        return HTTPResponse.NOT_FOUND
    items = []

    if cls == 'bulletin':
        items = actor.bulletin_relations
    elif cls == 'actor':
        items = actor.actor_relations
    elif cls == 'incident':
        items = actor.incident_relations
    elif cls == 'organization':
        items = actor.organization_relations

    # pagination
    start = (page - 1) * per_page
    end = start + per_page
    data = items[start:end]

    load_more = False if end >= len(items) else True

    if data:
        if cls == 'actor':
            data = [item.to_dict(exclude=actor) for item in data]
        else:
            data = [item.to_dict() for item in data]

    return json.dumps({'items': data, 'more': load_more}), 200


@admin.route('/api/socialmediaplatforms/', methods=['GET', 'POST'])
def api_social_media_platforms():
    """
    Endpoint to get all social media platforms
    :return: social media platforms in json format + success or error in case of failure
    """
    result = SocialMediaPlatform.query.all()
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/socialmediaplatform/')
def api_social_media_platform_create():
    """
    Endpoint to create a social media platform
    :return: success/error based on operation's result
    """
    platform = SocialMediaPlatform()
    platform.from_json(request.json['item'])
    result = platform.save()
    if result:
        return Response(json.dumps(result.to_dict()), content_type='application/json'), 200
    else:
        return 'Error creating social media platform', 417


@admin.get('/api/socialmediaplatform/<int:id>')
def api_social_media_platform_get(id):
    """
    Endpoint to get a single social media platform
    :param id: id of the social media platform
    :return: social media platform data in json format + success or error in case of failure
    """
    platform = SocialMediaPlatform.query.get(id)
    if not platform:
        return 'Not found', 404
    else:
        return Response(json.dumps(platform.to_dict()),
                    content_type='application/json'), 200


@admin.put('/api/socialmediaplatform/<int:id>')
def api_social_media_platform_update(id):
    """
    Endpoint to update a social media platform
    :param id: id of the social media platform to be updated
    :return: social media platform data in json format + success or error in case of failure
    """
    platform = SocialMediaPlatform.query.get(id)
    if platform is not None:
        platform = platform.from_json(request.json['item'])
        result = platform.save()
        if result:
            return json.dumps(result.to_dict()), 200
        else:
            return 'Error saving social media platform', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/socialmediaplatform/<int:id>')
def api_social_media_platform_delete(id):
    """
    Endpoint to delete a social media platform
    :param id: id of the social media platform to be deleted
    :return: success/error based on operation's result
    """
    platform = SocialMediaPlatform.query.get(id)
    if platform is not None:
        result = platform.delete()
        Activity.create(current_user, Activity.ACTION_DELETE, platform.to_mini(), 'social media platform')
        if result:
            return 'Deleted!', 200
        else:
            return 'Error deleting social media platform', 417
    else:
        return HTTPResponse.NOT_FOUND


@admin.route('/api/socialmediahandles/', methods=['GET', 'POST'])
def api_social_media_handles():
    """
    Endpoint to get all social media handles
    :return: social media handles in json format + success or error in case of failure
    """
    result = SocialMediaHandle.query.all()
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/socialmediahandle/')
def api_social_media_handle_create():
    """
    Endpoint to create a social media handle
    :return: success/error based on operation's result
    """
    handle = SocialMediaHandle()
    handle.from_json(request.json['item'])
    result = handle.save()
    if result:
        return Response(json.dumps(result.to_dict()),
                        content_type='application/json'), 200
    else:
        return 'Error creating social media handle', 417


@admin.get('/api/socialmediahandle/<int:id>')
def api_social_media_handle_get(id):
    """
    Endpoint to get a single social media handle
    :param id: id of the social media handle
    :return: social media handle data in json format + success or error in case of failure
    """
    handle = SocialMediaHandle.query.get(id)
    if not handle:
        return 'Not found', 404
    else:
        return Response(json.dumps(handle.to_dict()),
                    content_type='application/json'), 200


@admin.put('/api/socialmediahandle/<int:id>')
def api_social_media_handle_update(id):
    """
    Endpoint to update a social media handle
    :param id: id of the social media handle to be updated
    :return: social media handle data in json format + success or error in case of failure
    """
    handle = SocialMediaHandle.query.get(id)
    if handle is not None:
        handle = handle.from_json(request.json['item'])
        result = handle.save()
        if result:
            return json.dumps(result.to_dict()), 200
        else:
            return 'Error saving social media handle', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/socialmediahandle/<int:id>')
def api_social_media_handle_delete(id):
    """
    Endpoint to delete a social media handle
    :param id: id of the social media handle to be deleted
    :return: success/error based on operation's result
    """
    handle = SocialMediaHandle.query.get(id)
    if handle is not None:
        result = handle.delete()
        Activity.create(current_user, Activity.ACTION_DELETE, handle.to_mini(), 'social media handle')
        if result:
            return 'Deleted!', 200
        else:
            return 'Error deleting social media handle', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/sanction-regimes/', methods=['GET'])
def api_sanction_regimes():
    """
    Endpoint to get all sanction regimes
    :return: sanction regimes in json format + success or error in case of failure
    """
    result = SanctionRegime.query.all()
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/sanction-regimes/')
def api_sanction_regimes_create():
    """
    Endpoint to create a sanction regime
    :return: success/error based on operation's result
    """
    regime = SanctionRegime()
    regime.from_json(request.json['item'])
    result = regime.save()
    if result:
        return Response(json.dumps(result.to_dict()), content_type='application/json'), 200
    else:
        return 'There was an error creating the sanction regime', 500
    
@admin.get('/api/sanction-regimes/<int:id>')
def api_sanction_regime_get(id):
    """
    Endpoint to get a single sanction regime
    :param id: id of the sanction regime
    :return: sanction regime data in json format + success or error in case of failure
    """
    regime = SanctionRegime.query.get(id)

    if not regime:
        return HTTPResponse.NOT_FOUND
    else:
        return Response(json.dumps(regime.to_dict()),
                        content_type='application/json'), 200

@admin.put('/api/sanction-regimes/<int:id>')
def api_sanction_regime_update(id):
    """
    Endpoint to update a sanction regime
    :param id: id of the sanction regime to be updated
    :return: sanction regime data in json format + success or error in case of failure
    """
    regime = SanctionRegime.query.get(id)
    if regime is not None:
        regime = regime.from_json(request.json['item'])
        result = regime.save()
        if result:
            return json.dumps(result.to_dict()), 200
        else:
            return 'Error saving the sanction regime', 417
    else:
        return  HTTPResponse.NOT_FOUND
    
@admin.delete('/api/sanction-regimes/<int:id>')
def api_sanction_regime_delete(id):
    """
    Endpoint to delete a sanction regime
    :param id: id of the sanction regime to be deleted
    :return: success/error based on operation's result
    """
    regime = SanctionRegime.query.get(id)
    if regime is not None:
        result = regime.delete()
        Activity.create(current_user, Activity.ACTION_DELETE, regime.to_mini(), 'sanction regime')
        if result:
            return 'Deleted!', 200
        else:
            return 'Error deleting the sanction regime', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/sub-types/', methods=['GET'])
def api_sub_types():
    """
    Endpoint to get all sub types
    :return: sub types in json format + success or error in case of failure
    """
    result = ActorSubType.query.all()
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/sub-types/')
def api_sub_type_create():
    """
    Endpoint to create a sub type
    :return: success/error based on operation's result
    """
    sub_type = ActorSubType()
    sub_type.from_json(request.json['item'])
    result = sub_type.save()
    if result:
        return Response(json.dumps(result.to_dict()), content_type='application/json'), 200
    else:
        return 'There was an error creating the sub type', 500

@admin.get('/api/sub-types/<int:id>')
def api_sub_type_get(id):
    """
    Endpoint to get a single sub type
    :param id: id of the sub type
    :return: sub type data in json format + success or error in case of failure
    """
    sub_type = ActorSubType.query.get(id)

    if not sub_type:
        return HTTPResponse.NOT_FOUND
    else:
        return Response(json.dumps(sub_type.to_dict()),
                        content_type='application/json'), 200

@admin.put('/api/sub-types/<int:id>')
def api_sub_type_update(id):
    """
    Endpoint to update a sub type
    :param id: id of the sub type to be updated
    :return: sub type data in json format + success or error in case of failure
    """
    sub_type = ActorSubType.query.get(id)
    if sub_type is not None:
        sub_type = sub_type.from_json(request.json['item'])
        result = sub_type.save()
        if result:
            return json.dumps(result.to_dict()), 200
        else:
            return 'Error saving the sub type', 417
    else:
        return  HTTPResponse.NOT_FOUND

@admin.delete('/api/sub-types/<int:id>')
def api_sub_type_delete(id):
    """
    Endpoint to delete a sub type
    :param id: id of the sub type to be deleted
    :return: success/error based on operation's result
    """
    sub_type = ActorSubType.query.get(id)
    if sub_type is not None:
        result = sub_type.delete()
        Activity.create(current_user, Activity.ACTION_DELETE, sub_type.to_mini(), 'sub type')
        if result:
            return 'Deleted!', 200
        else:
            return 'Error deleting the sub type', 417

@admin.route('/api/consent-uses/', methods=['GET'])
def api_consent_uses():
    """
    Endpoint to get all consent uses
    :return: consent uses in json format + success or error in case of failure
    """
    result = ConsentUse.query.all()
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/consent-uses/')
def api_consent_uses_create():
    """
    Endpoint to create a consent use
    :return: success/error based on operation's result
    """
    consent_use = ConsentUse()
    consent_use.from_json(request.json['item'])
    result = consent_use.save()
    if result:
        return Response(json.dumps(result.to_dict()), content_type='application/json'), 200
    else:
        return 'There was an error creating the consent use', 500

@admin.get('/api/consent-uses/<int:id>')
def api_consent_use_get(id):
    """
    Endpoint to get a single consent use
    :param id: id of the consent use
    :return: consent use data in json format + success or error in case of failure
    """
    consent_use = ConsentUse.query.get(id)

    if not consent_use:
        return HTTPResponse.NOT_FOUND
    else:
        return Response(json.dumps(consent_use.to_dict()),
                        content_type='application/json'), 200

@admin.put('/api/consent-uses/<int:id>')
def api_consent_use_update(id):
    """
    Endpoint to update a consent use
    :param id: id of the consent use to be updated
    :return: consent use data in json format + success or error in case of failure
    """
    consent_use = ConsentUse.query.get(id)
    if consent_use is not None:
        consent_use = consent_use.from_json(request.json['item'])
        result = consent_use.save()
        if result:
            return json.dumps(result.to_dict()), 200
        else:
            return 'Error saving the consent use', 417
    else:
        return  HTTPResponse.NOT_FOUND

@admin.delete('/api/consent-uses/<int:id>')
def api_consent_use_delete(id):
    """
    Endpoint to delete a consent use
    :param id: id of the consent use to be deleted
    :return: success/error based on operation's result
    """
    consent_use = ConsentUse.query.get(id)
    if consent_use is not None:
        result = consent_use.delete()
        Activity.create(current_user, Activity.ACTION_DELETE, consent_use.to_mini(), 'consent use')
        if result:
            return 'Deleted!', 200
        else:
            return 'Error deleting the consent use', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/actormp/<int:id>', methods=['GET'])
def api_actor_mp_get(id):
    """
    Endpoint to get missing person data for an actor
    :param id: id of the actor
    :return: actor data in json format + success or error in case of failure
    """
    if request.method == 'GET':
        actor = Actor.query.get(id)
        if not actor:
            return HTTPResponse.NOT_FOUND
        else:
            return json.dumps(actor.mp_json()), 200


# Bulletin History Helpers

@admin.route('/api/bulletinhistory/<int:bulletinid>')
@requires('view', 'history')
def api_bulletinhistory(bulletinid):
    """
    Endpoint to get revision history of a bulletin
    :param bulletinid: id of the bulletin item
    :return: json feed of item's history , or error
    """
    result = BulletinHistory.query.filter_by(bulletin_id=bulletinid).order_by(desc(BulletinHistory.created_at)).all()
    # For standardization 
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


# Actor History Helpers 

@admin.route('/api/actorhistory/<int:actorid>')
@requires('view', 'history')
def api_actorhistory(actorid):
    """
        Endpoint to get revision history of an actor
        :param actorid: id of the actor item
        :return: json feed of item's history , or error
        """
    result = ActorHistory.query.filter_by(actor_id=actorid).order_by(desc(ActorHistory.created_at)).all()
    # For standardization 
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


# Incident History Helpers

@admin.route('/api/incidenthistory/<int:incidentid>')
@requires('view', 'history')
def api_incidenthistory(incidentid):
    """
        Endpoint to get revision history of an incident item
        :param incidentid: id of the incident item
        :return: json feed of item's history , or error
        """
    result = IncidentHistory.query.filter_by(incident_id=incidentid).order_by(desc(IncidentHistory.created_at)).all()
    # For standardization 
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

#Organization history

@admin.route('/api/organizationhistory/<int:organizationid>')
@requires('view', 'history')
def api_organizationhistory(organizationid):
    """
        Endpoint to get revision history of an organization
        :param organizationid: id of the organization item
        :return: json feed of item's history , or error
        """
    result = OrganizationHistory.query.filter_by(organization_id=organizationid).order_by(desc(OrganizationHistory.created_at)).all()
    # For standardization
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

# Location History Helpers

@admin.route('/api/locationhistory/<int:locationid>')
@requires('view', 'history')
def api_locationhistory(locationid):
    """
    Endpoint to get revision history of a location
    :param locationid: id of the location item
    :return: json feed of item's history , or error
    """
    result = LocationHistory.query.filter_by(location_id=locationid).order_by(desc(LocationHistory.created_at)).all()
    # For standardization
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


# user management routes

@admin.route('/api/users/')
@roles_accepted('Admin', 'Mod')
def api_users():
    """
    API endpoint to feed users data in json format , supports paging and search
    :return: success and json feed of items or error
    """
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)
    q = request.args.get('q')
    query = []
    if q is not None:
        query.append(User.name.ilike('%' + q + '%'))
    result = User.query.filter(*query)

    #Sort by request
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'
    
    #Users to Roles is a many-many relationship so get association table then sort
    if sort_by == 'roles':
        role_alias = aliased(Role)
        result = result.outerjoin(role_alias, User.roles)
        result = result.order_by(role_alias.name.desc() if sort_desc else role_alias.name)
    else:
        if hasattr(User, sort_by):
            result = result.order_by(getattr(User, sort_by).desc() if sort_desc else getattr(User, sort_by))
        else:
            return {'error': 'Invalid sort_by fied'}, 400

    result = result.paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() if current_user.has_role('Admin')
                          else item.to_compact()
                          for item in result.items],
                'perPage': per_page, 'total': result.total}

    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.route('/users/')
@roles_required('Admin')
def users():
    """
    Endpoint to render the users backend page
    :return: html page of the users backend.
    """
    return render_template('views/admin/users.html')


@admin.post('/api/user/')
@roles_required('Admin')
def api_user_create():
    """
    Endpoint to create a user item
    :return: success / error baesd on operation's outcome
    """
    # validate existing
    u = request.json.get('item')
    username = u.get('username')
    
    username_error = check_username_errors(username)
    if username_error is not None:
        return username_error

    exists = User.query.filter(User.username == username).first()
    if len(username) < 4:
        return 'Error, username too short', 417
    if len(username) > 32:
        return 'Error, username too long', 417
    if exists:
        return 'Error, username already exists', 417
    user = User()
    user.fs_uniquifier = uuid4().hex
    user.from_json(u)
    result = user.save()
    if result:
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, user.to_mini(), 'user')
        return F'User {username} has been created successfully', 200
    else:
        return 'Error creating user', 417


def check_username_errors(data):
    # validate illegal characters
    uclean = bleach.clean(data.strip(), strip=True)
    if uclean != data:
        return 'Illegal characters detected'

    # validate disallowed characters
    cats = [unicodedata.category(c)[0] for c in data]
    if any(cat not in ["L", "N"] and c != "." and c != "-" for cat, c in zip(cats, data)):
        return 'Disallowed characters detected'
    
    if (data.startswith('.') or data.startswith('-')):
        return 'Illegal character detected at beginning of username'
    
    if (data.endswith('.') or data.endswith('-')):
        return 'Illegal characted detected at end of username'
    
    return None


@admin.route('/api/checkuser/', methods=['POST'])
@roles_required('Admin')
def api_user_check():
    data = request.json.get('item')
    if not data:
        return 'Please select a username', 417

    username_error = check_username_errors(data)
    if username_error is not None:
        return username_error, 417
    
    u = User.query.filter(User.username == data).first()
    if u:
        return 'Username already exists', 417
    else:
        return 'Username ok', 200


@admin.put('/api/user/<int:uid>')
@roles_required('Admin')
def api_user_update(uid):
    """Endpoint to update a user."""

    user = User.query.get(uid)
    if user is not None:
        u = request.json.get('item')
        user = user.from_json(u)
        if user.save():
            # Record activity
            Activity.create(current_user, Activity.ACTION_UPDATE, user.to_mini(), 'user')
            return F'Saved User {user.id} {user.name}', 200
        else:
            return F'Error saving User {user.id} {user.name}', 417
    else:
        return HTTPResponse.NOT_FOUND


@admin.post('/api/password/')
def api_check_password():
    """
    API Endpoint to validate a password and check its strength

    :return: successful response if valid, else error response
    """
    # Retrieve the password from the request's JSON body
    password = request.json.get('password')

    # Check if the password is provided
    if not password:
        return 'No password provided', 400

    result = zxcvbn(password)
    score = result.get('score')
    if score >= current_app.config.get('SECURITY_ZXCVBN_MINIMUM_SCORE'):
        return 'Password is ok', 200
    else:
        return 'Weak Password Score', 409





@admin.post('/api/user/force-reset')
@roles_required('Admin')
def api_user_force_reset():
    item = request.json.get("item")
    if not item:
        abort(400)
    user = User.query.get(item.get('id'))
    if not user:
        abort(400)
    if reset_key := user.security_reset_key:
        message = f'Forced password reset already requested: {reset_key}'
        return Response(message, mimetype='text/plain')
    user.set_security_reset_key()
    message = f'Forced password reset has been set for user {user.username}'
    return Response(message, mimetype='text/plain')

@admin.post('/api/user/force-reset-all')
@roles_required('Admin')
def api_user_force_reset_all():
    """
    sets a redis flag to force password reset for all users
    :return: success response after setting all redis flags (if not already set)
    """
    for user in User.query.all():
        # check if user already has a password reset flag
        if not user.security_reset_key:
            user.set_security_reset_key()
    return 'Forced password reset has been set for all users', 200



@admin.delete('/api/user/<int:id>')
@roles_required('Admin')
def api_user_delete(id):
    """
    Endpoint to delete a user
    :param id: id of the user to be deleted
    :return: success/error
    """
    if request.method == 'DELETE':
        user = User.query.get(id)
        if user.active:
            return 'User is active, make inactive before deleting', 403
        user.delete()

        # Record activity
        Activity.create(current_user, Activity.ACTION_DELETE, user.to_mini(), 'user')
        return 'Deleted!', 200


# Roles routes
@admin.route('/roles/')
@roles_required('Admin')
def roles():
    """
    Endpoint to redner roles backend page
    :return: html of the page
    """
    return render_template('views/admin/roles.html')


@admin.route('/api/roles/', defaults={'page': 1})
@admin.route('/api/roles/<int:page>/')
def api_roles(page):
    """
    API endpoint to feed roles items in josn format - supports paging and search
    :param page: db query offset
    :return: successful json feed or error
    """
    query = []
    q = request.args.get('q', None)
    if q is not None:
        query.append(
            Role.name.ilike('%' + q + '%')
        )
    # if custom is set, exclude system roles
    is_custom = request.args.get('custom', False)
    if is_custom:
        query.append(
            Role.name.notin_(['Admin', 'Mod', 'DA'])
        )
    # if my_roles_only is set, only show roles assigned to the current user
    my_roles_only = request.args.get('my_roles_only', False)
    if my_roles_only and current_user.roles:
        query.append(
            Role.id.in_([r.id for r in current_user.roles])
        )
    result = Role.query.filter(*query)

    #Sort by request
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'

    if hasattr(Role, sort_by):
        result = result.order_by(getattr(Role, sort_by).desc() if sort_desc else getattr(Role, sort_by))
    else:
        return {'error': 'Invalid sort_by fied'}, 400

    result = result.paginate(page=page, per_page=PER_PAGE, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': PER_PAGE, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/role/')
@roles_required('Admin')
def api_role_create():
    """
    Endpoint to create a role item
    :return: success/error
    """
    role = Role()
    created = role.from_json(request.json['item'])
    if created.save():
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, role.to_mini(), 'role')
        return 'Created!', 200

    else:
        return 'Save Failed', 417


@admin.put('/api/role/<int:id>')
@roles_required('Admin')
def api_role_update(id):
    """
    Endpoint to update a role item
    :param id: id of the role to be updated
    :return: success / error
    """
    role = Role.query.get(id)
    if role is None:
        return HTTPResponse.NOT_FOUND

    if role.name in ['Admin', 'Mod', 'DA']:
        return 'Cannot edit System Roles', 403

    role = role.from_json(request.json['item'])
    role.save()
    # Record activity
    Activity.create(current_user, Activity.ACTION_UPDATE, role.to_mini(), 'role')
    return 'Saved!', 200


@admin.delete('/api/role/<int:id>')
@roles_required('Admin')
def api_role_delete(id):
    """
    Endpoint to delete a role item
    :param id: id of the role to be deleted
    :return: success / error
    """
    role = Role.query.get(id)

    if role is None:
        return HTTPResponse.NOT_FOUND

    # forbid deleting system roles
    if role.name in ['Admin', 'Mod', 'DA']:
        return 'Cannot delete System Roles', 403
    # forbid delete roles assigned to restricted items
    if role.bulletins.first() or role.actors.first() or role.incidents.first():
        return 'Role assigned to restricted items', 403

    role.delete()
    # Record activity
    Activity.create(current_user, Activity.ACTION_DELETE, role.to_mini(), 'role')
    return 'Deleted!', 200


@admin.post('/api/role/import/')
@roles_required('Admin')
def api_role_import():
    """
    Endpoint to import role items from a CSV file
    :return: success / error
    """
    if 'csv' in request.files:
        Role.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 400


# Incident routes
@admin.route('/investigations/', defaults={'id': None})
@admin.route('/investigations/<int:id>')
def incidents(id):
    """
    Endpoint to render incidents backend page
    :return: html page of the incidents backend management
    """
    # Pass relationship information
    atobInfo = [item.to_dict() for item in AtobInfo.query.all()]
    btobInfo = [item.to_dict() for item in BtobInfo.query.all()]
    atoaInfo = [item.to_dict() for item in AtoaInfo.query.all()]
    itobInfo = [item.to_dict() for item in ItobInfo.query.all()]
    itoaInfo = [item.to_dict() for item in ItoaInfo.query.all()]
    itoiInfo = [item.to_dict() for item in ItoiInfo.query.all()]
    otooInfo = [item.to_dict() for item in OtooInfo.query.all()]
    otobInfo = [item.to_dict() for item in OtobInfo.query.all()]
    otoiInfo = [item.to_dict() for item in OtoiInfo.query.all()]
    otoaInfo = [item.to_dict() for item in OtoaInfo.query.all()]
    statuses = [item.to_dict() for item in WorkflowStatus.query.all()]
    return render_template('views/admin/incidents.html',
                           atobInfo=atobInfo,
                           btobInfo=btobInfo,
                           atoaInfo=atoaInfo,
                           itobInfo=itobInfo,
                           itoaInfo=itoaInfo,
                           itoiInfo=itoiInfo,
                           otobInfo=otobInfo,
                           otooInfo=otooInfo,
                           otoiInfo=otoiInfo,
                           otoaInfo=otoaInfo,
                           statuses=statuses)


@admin.route('/api/incidents/', methods=['POST', 'GET'])
def api_incidents():
    """Returns actors in JSON format, allows search and paging."""
    query = []

    su = SearchUtils(request.json, cls='Incident')

    query = su.get_query()
    result = Incident.query.filter(or_(Incident.deleted == False, Incident.deleted.is_(None))).filter(*query)

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'

    #Adjust query for sorting by a field in a related model if needed
    if sort_by == 'assigned_to.name':
        result = result.outerjoin(User, Incident.assigned_to_id == User.id)
        result = result.order_by(User.name.desc() if sort_desc else User.name)
    elif sort_by == "roles":
        #Incidents to Roles is a many-many relationship so get association table then sort
        role_alias = aliased(Role)
        result = result.outerjoin(role_alias, Incident.roles)
        result = result.order_by(role_alias.name.desc() if sort_desc else role_alias.name)
    else:
        if hasattr(Incident, sort_by):
            result = result.order_by(getattr(Incident, sort_by).desc() if sort_desc else getattr(Incident, sort_by))
        else:
            return {'error': 'Invalid sort_by fied'}, 400
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    result = result.paginate(page=page, per_page=per_page, count=True)
    # Select json encoding type
    mode = request.args.get('mode', '1')
    response = {'items': [item.to_dict(mode=mode) for item in result.items], 'perPage': per_page, 'total': result.total}

    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.post('/api/incident/')
@roles_accepted('Admin', 'DA')
def api_incident_create():
    """API endpoint to create an incident."""

    incident = Incident()
    # assign to creator by default
    incident.assigned_to_id = current_user.id
    # assignment will be overwritten if it is specified in the creation request
    incident.from_json(request.json['item'])
    incident.save()
    # the below will create the first revision by default
    incident.create_revision()
    # Record activity
    Activity.create(current_user, Activity.ACTION_CREATE, incident.to_mini(), 'incident')
    return F'Created Investigation #{incident.id}', 200


# update incident endpoint
@admin.put('/api/incident/<int:id>')
@roles_accepted('Admin', 'DA')
def api_incident_update(id):
    """API endpoint to update an incident."""

    incident = Incident.query.get(id)

    if incident is not None:
        if not current_user.can_access(incident):
            return 'Restricted Access', 403
        incident = incident.from_json(request.json['item'])
        # Create a revision using latest values
        # this method automatically commits
        # incident changes (referenced)
        if incident:
            incident.create_revision()
            # Record activity
            Activity.create(current_user, Activity.ACTION_UPDATE, incident.to_mini(), 'incident')
            return F'Saved Investigation #{id}', 200
        else:
            return F'Error saving Investigation {id}', 417
    else:
        return HTTPResponse.NOT_FOUND


@admin.delete('/api/incident/<int:id>')
@roles_required('Admin')
def api_incidnet_delete(id):
    """
    Endpoint to delete an incident
    :param id: id of the incident to delete
    :return: success/error based on operation's result
    """
    incident = Incident.query.get(id)
    if incident is None:
        return HTTPResponse.NOT_FOUND
    # Record Activity
    Activity.create(current_user, Activity.ACTION_DELETE, incident.to_mini(), 'incident')
    incident.deleted = True
    incident.create_revision()
    return F'Deleted Investigation #{incident.id}', 200


# Add/Update review incident endpoint
@admin.put('/api/incident/review/<int:id>')
@roles_accepted('Admin', 'DA')
def api_incident_review_update(id):
    """
    Endpoint to update an incident review item
    :param id: id of the incident
    :return: success / error
    """
    incident = Incident.query.get(id)
    if incident is not None:
        if not current_user.can_access(incident):
            return 'Restricted Access', 403

        incident.review = request.json['item']['review'] if 'review' in request.json['item'] else ''
        incident.review_action = request.json['item']['review_action'] if 'review_action' in request.json[
            'item'] else ''

        incident.status = 'Peer Reviewed'
        if incident.save():
            # Create a revision using latest values
            # this method automatically commi
            # incident changes (referenced)
            incident.create_revision()
            # Record activity
            Activity.create(current_user, Activity.ACTION_UPDATE, incident.to_mini(), 'incident')
            return F'Bulletin review updated #{id}', 200
        else:
            return F'Error saving Investigation #{id}\'s Review', 417
    else:
        return HTTPResponse.NOT_FOUND


# bulk update incident endpoint
@admin.put('/api/incident/bulk/')
@roles_accepted('Admin', 'Mod')
def api_incident_bulk_update():
    """endpoint to handle bulk incidents updates."""

    ids = request.json['items']
    bulk = request.json['bulk']

    # non-intrusive hard validation for access roles based on user
    if not current_user.has_role('Admin'):
        # silently discard access roles
        if not current_user.has_role('Mod'):
            bulk.pop('rolesReplace', None)
            bulk.pop('roles', None)
        bulk.pop('restrictRelated', None)

    if ids and len(bulk):
        job = bulk_update_incidents.delay(ids, bulk, current_user.id)
        # store job id in user's session for status monitoring
        key = F'user{current_user.id}:{job.id}'
        rds.set(key, job.id)
        # expire in 3 hour
        rds.expire(key, 60 * 60 * 3)
        return 'Bulk update queued successfully', 200
    else:
        return 'No items selected, or nothing to update', 417


# get one incident
@admin.get('/api/incident/<int:id>')
def api_incident_get(id):
    """
    Endopint to get a single incident by id
    :param id: id of the incident item
    :return: successful incident item in json format or error
    """
    incident = Incident.query.get(id)
    if not incident:
        return 'Not Found', 404
    else:
        mode = request.args.get('mode', None)
        if current_user.can_access(incident):
            return json.dumps(incident.to_dict(mode)), 200
        else:
            # block access altogether here, doesn't make sense to send only the id
            return 'Restricted Access', 403


# get incident relations
@admin.get('/api/incident/relations/<int:id>')
def incident_relations(id):
    """
    Endpoint to return related entities of an Incident
    :return:
    """
    cls = request.args.get('class', None)
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', REL_PER_PAGE, int)
    if not cls or cls not in relation_classes:
        return HTTPResponse.NOT_FOUND
    incident = Incident.query.get(id)
    if not incident:
        return HTTPResponse.NOT_FOUND
    items = []

    if cls == 'bulletin':
        items = incident.bulletin_relations
    elif cls == 'actor':
        items = incident.actor_relations
    elif cls == 'incident':
        items = incident.incident_relations
    elif cls == 'organization':
        items = incident.organization_relations

    # add support for loading all relations at once
    if page == 0:
        if cls == 'incident':
            data = [item.to_dict(exclude=incident) for item in items]
        else:
            data = [item.to_dict() for item in items]

        return json.dumps({'items': data, 'more': False}), 200

    # pagination
    start = (page - 1) * per_page
    end = start + per_page
    data = items[start:end]

    load_more = False if end >= len(items) else True

    if data:
        if cls == 'incident':
            data = [item.to_dict(exclude=incident) for item in data]
        else:
            data = [item.to_dict() for item in data]

    return json.dumps({'items': data, 'more': load_more}), 200


@admin.route('/api/incident/import/', methods=['POST'])
@roles_required('Admin')
def api_incident_import():
    """
    Endpoint to handle incident imports.
    :return: successful response or error code in case of failure.
    """
    if 'csv' in request.files:
        Incident.import_csv(request.files.get('csv'))
        return 'Success', 200
    else:
        return 'Error', 417


#Organization routes
@admin.route('/organizations/', defaults={'id': None})
@admin.route('/organizations/<int:id>')
def organizations(id):
    """
    Endpoint to render organizations backend page
    :return: html page of the organizations backend management
    """
    # Pass relationship information
    atobInfo = [item.to_dict() for item in AtobInfo.query.all()]
    btobInfo = [item.to_dict() for item in BtobInfo.query.all()]
    atoaInfo = [item.to_dict() for item in AtoaInfo.query.all()]
    itobInfo = [item.to_dict() for item in ItobInfo.query.all()]
    itoaInfo = [item.to_dict() for item in ItoaInfo.query.all()]
    itoiInfo = [item.to_dict() for item in ItoiInfo.query.all()]
    otooInfo = [item.to_dict() for item in OtooInfo.query.all()]
    otobInfo = [item.to_dict() for item in OtobInfo.query.all()]
    otoiInfo = [item.to_dict() for item in OtoiInfo.query.all()]
    otoaInfo = [item.to_dict() for item in OtoaInfo.query.all()]
    statuses = [item.to_dict() for item in WorkflowStatus.query.all()]
    return render_template('views/admin/organizations.html',
                           atobInfo=atobInfo,
                           btobInfo=btobInfo,
                           atoaInfo=atoaInfo,
                           itobInfo=itobInfo,
                           itoaInfo=itoaInfo,
                           itoiInfo=itoiInfo,
                           otobInfo=otobInfo,
                           otooInfo=otooInfo,
                           otoiInfo=otoiInfo,
                           otoaInfo=otoaInfo,
                           statuses=statuses)

@admin.route('/api/organizations/', methods=['POST', 'GET'])
def api_organizations():
    """Returns organizations in JSON format, allows search and paging."""
    # TODO  implement organization search utils
    if request.method == 'POST':
        su = SearchUtils(request.json, cls='Organization')
        queries, ops = su.get_query()
        result = Organization.query.filter(or_(Organization.deleted == False, Organization.deleted.is_(None))).filter(*queries.pop(0))

        # nested queries
        if len(queries) > 0:
            while queries:
                nextOp = ops.pop(0)
                nextQuery = queries.pop(0)
                if nextOp == 'union':
                    result = result.union(Organization.query.filter(*nextQuery))
                elif nextOp == 'intersect':
                    result = result.intersect(Organization.query.filter(*nextQuery))
    else:
        result = Organization.query.filter(or_(Organization.deleted == False, Organization.deleted.is_(None)))

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'
    elif sort_by == '_status':
        sort_by = 'status'

    #Adjust query for sorting by a field in a related model if needed
    if sort_by == "assigned_to.name":
        result = result.outerjoin(User, Organization.assigned_to_id == User.id)
        result = result.order_by(User.name.desc() if sort_desc else User.name)
    elif sort_by == 'roles':
        #Organizations to Roles is a many-many relationship so get association table then sort
        role_alias = aliased(Role)
        result = result.outerjoin(role_alias, Organization.roles)
        result = result.order_by(role_alias.name.desc() if sort_desc else role_alias.name)
    else:
        if hasattr(Organization, sort_by):
            result = result.order_by(getattr(Organization, sort_by).desc() if sort_desc else getattr(Organization, sort_by))
        else:
            return {'error': 'Invalid sort_by fied'}, 400

    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)
    result = result.paginate(page=page, per_page=per_page, count=True)

    # Select json encoding type
    mode = request.args.get('mode', '1')
    response = {'items': [item.to_dict(mode=mode) for item in result.items], 'perPage': per_page, 'total': result.total}

    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.get('/api/organization/<int:id>')
def api_organization_get(id):
    """
    Endpoint to get a single organization by id
    :param id: id of the organization item
    :return: successful organization item in json format or error
    """
    organization = Organization.query.get(id)
    if not organization:
        return HTTPResponse.NOT_FOUND
    else:
        return json.dumps(organization.to_dict()), 200

@admin.post('/api/organization/')
@roles_accepted('Admin', 'DA')
def api_organization_create():
    """
    Endpoint to create an organization item
    :return: success/error based on the operation's result
    """
    organization = Organization()
    # assign organization to creator by default
    organization.assigned_to_id = current_user.id
    # assignment will be overwritten if it is specified in the creation request
    try:
        organization.from_json(request.json['item'])
    except Exception as e:
        return f'Error creating organization: {e}', 400
    result = organization.save()
    if result:
        # the below will create the first revision by default
        organization.create_revision()
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, organization.to_mini(), 'organization')
        return F'Created Organization #{organization.id}', 200
    else:
        return 'Error creating organization', 417

@admin.put('/api/organization/<int:id>')
@roles_accepted('Admin', 'DA')
def api_organization_update(id):
    """
    Endpoint to update an Organization item
    :param id: id of the organization to be updated
    :return: success/error
    """
    organization = Organization.query.get(id)
    if organization is not None:
        # check for restrictions
        if not current_user.can_access(organization):
            return 'Restricted Access', 403

        try:
            organization = organization.from_json(request.json['item'])
        except Exception as e:
            return f'Error updating organization: {e}', 400
        # Create a revision using latest values
        # this method automatically commits
        # organization changes (referenced)
        if organization:
            organization.create_revision()
            # Record activity
            Activity.create(current_user, Activity.ACTION_UPDATE, organization.to_mini(), 'organization')
            return F'Saved Organization #{organization.id}', 200
        else:
            return F'Error saving Organization #{id}', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.delete('/api/organization/<int:id>')
@roles_required('Admin')
def api_organization_delete(id):
    """
    Endpoint to delete an organization
    :param id: id of the organization to delete
    :return: success/error based on operation's result
    """
    organization = Organization.query.get(id)
    if organization is None:
        return HTTPResponse.NOT_FOUND
    # Record Activity
    Activity.create(current_user, Activity.ACTION_DELETE, organization.to_mini(), 'organization')
    organization.deleted = True
    organization.create_revision()
    return F'Deleted Organization #{organization.id}', 200

@admin.route('/api/organization/assignother/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_organization_assign(id):
    """assign an organization to another user"""
    organization = Organization.query.get(id)

    if not current_user.can_access(organization):
        return 'Restricted Access', 403

    if organization:
        i = request.json.get('organization')
        if not i or not i.get('assigned_to_id'):
            return 'No user selected',  400
        # update organization assignement
        organization.assigned_to_id = i.get('assigned_to_id')
        organization.comments = i.get('comments', '')

        # Change status to assigned if needed
        if organization.status == 'Machine Created' or organization.status == 'Human Created':
            organization.status = 'Assigned'

        # Create a revision using latest values
        # this method automatically commits
        # organization changes (referenced)
        organization.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, organization.to_mini(), 'organization')
        return F'Saved Organization #{organization.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/organization/assign/<int:id>', methods=['PUT'])
@roles_accepted('Admin', 'DA')
def api_organization_self_assign(id):
    """ self assign an organization to the user"""

    # permission check
    if not current_user.can_self_assign:
        return 'User not allowed to self assign', 400

    organization = Organization.query.get(id)

    if not current_user.can_access(organization):
        return 'Restricted Access', 403

    if organization:
        a = request.json.get('organization')
        # workflow check
        if organization.assigned_to_id and organization.assigned_to.active:
            return 'Item already assigned to an active user', 400

        # update bulletin assignement
        organization.assigned_to_id = current_user.id
        organization.comments = a.get('comments')

        # Change status to assigned if needed
        if organization.status == 'Machine Created' or organization.status == 'Human Created':
            organization.status = 'Assigned'

        organization.create_revision()

        # Record Activity
        Activity.create(current_user, Activity.ACTION_UPDATE, organization.to_mini(), 'organization')
        return F'Saved Organization #{organization.id}', 200
    else:
        return HTTPResponse.NOT_FOUND

@admin.put('/api/organization/bulk/')
@roles_accepted('Admin', 'Mod')
def api_organization_bulk_update():
    """
    Endpoint to bulk update organizations
    :return: success/error
    """

    ids = request.json['items']
    bulk = request.json['bulk']

    # non-intrusive hard validation for access roles based on user
    if not current_user.has_role('Admin') and not current_user.has_role('Mod'):
        # silently discard access roles
        bulk.pop('roles', None)

    if ids and len(bulk):
        job = bulk_update_organizations.delay(ids, bulk, current_user.id)
        # store job id in user's session for status monitoring
        key = F'user{current_user.id}:{job.id}'
        rds.set(key, job.id)
        # expire in 3 hour
        rds.expire(key, 60 * 60 * 3)
        return 'Bulk update queued successfully.', 200
    else:
        return 'No items selected, or nothing to update', 417

# Add/Update review organization endpoint
@admin.put('/api/organization/review/<int:id>')
@roles_accepted('Admin', 'DA')
def api_organization_review_update(id):
    """
    Endpoint to update a organization review
    :param id: id of the organization
    :return: success/error based on the outcome
    """
    organization = Organization.query.get(id)
    if organization is not None:
        if not current_user.can_access(organization):
            return 'Restricted Access', 403

        organization.review = request.json['item']['review'] if 'review' in request.json['item'] else ''
        organization.review_action = request.json['item']['review_action'] if 'review_action' in request.json[
            'item'] else ''

        if organization.status == 'Peer Review Assigned':
            organization.comments = 'Added Peer Review'
        if organization.status == 'Peer Reviewed':
            organization.comments = 'Updated Peer Review'

        organization.status = 'Peer Reviewed'

        # append refs
        refs = request.json.get('item', {}).get('revrefs', [])

        organization.ref = organization.ref + refs

        if organization.save():
            # Create a revision using latest values
            # this method automatically commits
            #  organization changes (referenced)           
            organization.create_revision()

            # Record Activity
            Activity.create(current_user, Activity.ACTION_UPDATE, organization.to_mini(), 'organization')
            return F'Organization review updated #{organization.id}', 200
        else:
            return F'Error saving Organization #{id}', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.get('/api/organization/relations/<int:id>')
def organization_relations(id):
    """
    Endpoint to return related entities of an Organization
    :return:
    """
    cls = request.args.get('class', None)
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', REL_PER_PAGE, int)
    if not cls or cls not in relation_classes:
        return HTTPResponse.NOT_FOUND
    organization = Organization.query.get(id)
    if not organization:
        return HTTPResponse.NOT_FOUND
    items = []

    if cls == 'bulletin':
        items = organization.bulletin_relations
    elif cls == 'actor':
        items = organization.actor_relations
    elif cls == 'incident':
        items = organization.incident_relations
    elif cls == 'organization':
        items = organization.organization_relations

    # pagination
    start = (page - 1) * per_page
    end = start + per_page
    data = items[start:end]

    load_more = False if end >= len(items) else True

    if data:
        if cls == 'organization':
            data = [item.to_dict(exclude=organization) for item in data]
        else:
            data = [item.to_dict() for item in data]

    return json.dumps({'items': data, 'more': load_more}), 200

# Organization Role routes
@admin.post('/api/organization-roles/')
@roles_accepted('Admin', 'DA')
def api_organization_role_create():
    """
    Endpoint to create an organization item
    :return: success/error based on the operation's result
    """
    organization_role = OrganizationRole()
    if not request.json:
        return 'No data provided', 400
    # check access to organization
    if request.json['item'].get('organization_id'):
        organization = Organization.query.get(request.json['item']['organization_id'])
        if not current_user.can_access(organization):
            return 'Restricted Access', 403
    # assignment will be overwritten if it is specified in the creation request
    try:
        organization_role.from_json(request.json['item'])
    except Exception as e:
        return f'Error creating organization: {e}', 400
    result = organization_role.save()
    if result:
        return result.to_dict(), 200
    else:
        return 'Error creating organization', 417

@admin.route('/api/organization-types/', methods=['GET'])
def api_organization_types():
    """
    Endpoint to get all organization types
    :return: organizaiton types in json format + success or error in case of failure
    """
    result = OrganizationType.query.all()
    response = {'items': [item.to_dict() for item in result]}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

@admin.post('/api/organization-types/')
def api_organization_type_create():
    """
    Endpoint to create a organization type
    :return: success/error based on operation's result
    """
    organization_type = OrganizationType()
    organization_type.from_json(request.json['item'])
    result = organization_type.save()
    if result:
        return Response(json.dumps(result.to_dict()), content_type='application/json'), 200
    else:
        return 'There was an error creating the organization type', 500

@admin.get('/api/organization-types/<int:id>')
def api_organization_type_get(id):
    """
    Endpoint to get a single organization type
    :param id: id of the organization type
    :return: organization type data in json format + success or error in case of failure
    """
    organization_type = OrganizationType.query.get(id)

    if not organization_type:
        return HTTPResponse.NOT_FOUND
    else:
        return Response(json.dumps(organization_type.to_dict()),
                        content_type='application/json'), 200

@admin.put('/api/organization-types/<int:id>')
def api_organization_type_update(id):
    """
    Endpoint to update a organization type
    :param id: id of the organization type to be updated
    :return: organization type data in json format + success or error in case of failure
    """
    organization_type = OrganizationType.query.get(id)
    if organization_type is not None:
        organization_type = organization_type.from_json(request.json['item'])
        result = organization_type.save()
        if result:
            return json.dumps(result.to_dict()), 200
        else:
            return 'Error saving the organization type', 417
    else:
        return  HTTPResponse.NOT_FOUND

@admin.delete('/api/organization-types/<int:id>')
def api_oganization_type_delete(id):
    """
    Endpoint to delete a organization type
    :param id: id of the organization type to be deleted
    :return: success/error based on operation's result
    """
    organization_type = OrganizationType.query.get(id)
    if organization_type is not None:
        result = organization_type.delete()
        Activity.create(current_user, Activity.ACTION_DELETE, organization_type.to_mini(), 'organization type')
        if result:
            return 'Deleted!', 200
        else:
            return 'Error deleting the organization type', 417

def api_base_info_route(cls):
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)

    query = []
    result = cls.query.filter(
        *query).order_by(-cls.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200

def api_base_info_create(cls):
    item = cls()
    item.from_json(request.json['item'])

    if item.save():
        return F'Item created successfully ID ${item.id} !', 200
    else:
        return 'Creation failed.', 417

def api_base_info_update(cls, id):
    item = cls.query.get(id)

    if item:
        item.from_json(request.json.get('item'))
        if item.save():
            return 'Updated !', 200
        else:
            return 'Error saving item', 417
    else:
        return HTTPResponse.NOT_FOUND

@admin.route('/api/otooinfos/', methods=['GET', 'POST'])
def api_otooinfos():
    return api_base_info_route(OtooInfo)

@admin.post('/api/otooinfo')
@roles_required('Admin')
def api_otooinfo_create():
    return api_base_info_create(OtooInfo)

@admin.put('/api/otooinfo/<int:id>')
@roles_required('Admin')
def api_otooinfo_update(id):
    return api_base_info_update(OtooInfo, id)

@admin.route('/api/otobinfos/', methods=['GET', 'POST'])
def api_otobinfos():
    return api_base_info_route(OtobInfo)

@admin.post('/api/otobinfo')
@roles_required('Admin')
def api_otobinfo_create():
    return api_base_info_create(OtobInfo)

@admin.put('/api/otobinfo/<int:id>')
@roles_required('Admin')
def api_otobinfo_update(id):
    return api_base_info_update(OtobInfo, id)

@admin.route('/api/otoainfos/', methods=['GET', 'POST'])
def api_otoainfos():
    return api_base_info_route(OtoaInfo)

@admin.post('/api/otoainfo')
@roles_required('Admin')
def api_otoainfo_create():
    return api_base_info_create(OtoaInfo)

@admin.put('/api/otoainfo/<int:id>')
@roles_required('Admin')
def api_otoainfo_update(id):
    return api_base_info_update(OtoaInfo, id)

@admin.route('/api/otoiinfos/', methods=['GET', 'POST'])
def api_otoiinfos():
    return api_base_info_route(OtoiInfo)

@admin.post('/api/otoiinfo')
@roles_required('Admin')
def api_otoiinfo_create():
    return api_base_info_create(OtoiInfo)

@admin.put('/api/otoiinfo/<int:id>')
@roles_required('Admin')
def api_otoiinfo_update(id):
    return api_base_info_update(OtoiInfo, id)

# Activity routes
@admin.route('/activity/')
@roles_required('Admin')
def activity():
    """
    Endpoint to render activity backend page
    :return: html of the page
    """
    return render_template('views/admin/activity.html')


@admin.route('/api/activity', methods=['POST', 'GET'])
@roles_required('Admin')
def api_activity():
    """
    API endpoint to feed activity items in json format, supports paging and filtering by tag
    :return: successful json feed or error
    """
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)
    query = []
    tag = request.json.get('tag', None)
    if tag:
        query.append(Activity.tag == tag)
    result = Activity.query.filter(*query)

    #Sort by request property
    sort_by = request.args.get('sort_by', 'id')
    sort_desc = request.args.get('sort_desc', 'false').lower() == 'true'
    if sort_by == '':
        sort_by = 'id'
    if hasattr(Activity, sort_by):
        #Check if its sorting by subject then we have to cast to a string because it's formatted as JSON in the DB
        if sort_by == 'subject':
            result = result.order_by(cast(Activity.subject['class'], String).desc().nullslast()) if sort_desc else result.order_by(cast(Activity.subject['class'], String).nullslast())
        else:
            result = result.order_by(getattr(Activity, sort_by).desc() if sort_desc else getattr(Activity, sort_by))
    else:
        return {'error': 'Invalid sort_by fied'}, 400

    result = result.paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.route('/api/bulk/status/')
def bulk_status():
    """Endpoint to get status update about background bulk operations"""
    uid = current_user.id
    cursor, jobs = rds.scan(0, F'user{uid}:*', 1000)
    tasks = []
    for key in jobs:
        result = {}
        id = key.decode('utf-8').split(':')[-1]
        type = request.args.get('type')
        status = None
        if type == 'bulletin':
            status = bulk_update_bulletins.AsyncResult(id).status
        elif type == 'actor':
            status = bulk_update_incidents.AsyncResult(id).status
        elif type == 'incident':
            status = bulk_update_actors.AsyncResult(id).status
        elif type == 'organization':
            status = bulk_update_organizations.AsyncResult(id).status
        else:
            return HTTPResponse.NOT_FOUND

        # handle job failure
        if status == 'FAILURE':
            rds.delete(key)
        if status != 'SUCCESS':
            result['id'] = id
            result['status'] = status
            tasks.append(result)

        else:
            rds.delete(key)
    return json.dumps(tasks)


# Saved Searches
@admin.route('/api/queries/')
def api_queries():
    """
    Endpoint to get user saved searches
    :return: successful json feed of saved searches or error
    """
    user_id = current_user.id
    query_type = request.args.get('type')
    if query_type not in Query.TYPES:
        return 'Invalid query type', 400
    queries = Query.query.filter(Query.user_id == user_id, Query.query_type == query_type)
    return json.dumps([query.to_dict() for query in queries]), 200


@admin.get('/api/query/<string:name>/exists')
def api_query_check_name_exists(name: str):
    """
    API Endpoint check if a query with that provided name exists.
    Queries are tied to the current (request) user.
    :return: true if exists, else false
    """
    if Query.query.filter_by(
            name=name,
            user_id=current_user.id
    ).first():
        return "Query name already exists!", 409

    return "Query name is available", 200


@admin.post('/api/query/')
def api_query_create():
    """
    API Endpoint save a query search object (advanced search)
    :return: success if save is successful, error otherwise
    """
    q = request.json.get('q', None)
    name = request.json.get('name', None)
    query_type = request.json.get('type')
    # current saved searches types
    if query_type not in Query.TYPES:
        return 'Invalid Request', 400
    if q and name:
        query = Query()
        query.name = name
        query.data = q
        query.query_type = query_type
        query.user_id = current_user.id
        query.save()
        return 'Query successfully saved!', 200
    else:
        return 'Error parsing query data', 417


@admin.put('/api/query/<string:name>')
def api_query_update(name: str):
    """
    API Endpoint update a query search object (advanced search).
    Updated searches are tied to the current (request) user.
    :return: success if update is successful, error otherwise
    """
    if not (q := request.json.get('q')):
        return "q parameter not provided", 417

    query = Query.query.filter(and_(
        Query.user_id == current_user.id,
        Query.name == name,
    ))

    if query_found := query.first():
        query_found.data = q
    else:
        return f"Query {name} not found", 404

    if query_found.save():
        return f"Query {name} updated!", 200

    return f"Query {name} save failed", 409


@admin.delete('/api/query/<string:name>')
def api_query_delete(name: str):
    """
    API Endpoint delete a query search object (advanced search).
    Deleted searches are tied to the current (request) user.
    :return: success if deletion is successful, error otherwise
    """
    query = Query.query.filter(and_(
        Query.user_id == current_user.id,
        Query.name == name,
    ))

    if not (query_found := query.first()):
        return f"Query: {name} not found", 404

    if query_found.delete():
        return f"Query {name} deleted!", 200

    return f"Query {name} delete failed", 409


@admin.get('/api/relation/info')
def relation_info():
    table = request.args.get('type')

    # Define a dictionary to map 'type' to query classes
    table_map = {
        'atob': AtobInfo,
        'atoa': AtoaInfo,
        'btob': BtobInfo,
        'itoi': ItoiInfo,
        'itob': ItobInfo,
        'itoa': ItoaInfo,
        'otoi': OtoiInfo,
        'otob': OtobInfo,
        'otoo': OtooInfo,
        'otoa': OtoaInfo,
    }

    # Check if 'table' is a valid key in the table_map dictionary
    if table in table_map:
        query_class = table_map[table]
        return json.dumps([item.to_dict() for item in query_class.query.all()])
    else:
        return json.dumps({'error': 'Invalid table type'})


@admin.get('/system-administration/')
@auth_required(within=15, grace=0)
@roles_accepted('Admin')
def system_admin():
    """Endpoint for system administration."""
    return render_template('views/admin/system-administration.html')


@admin.get('/api/appconfig/')
@roles_accepted('Admin')
def api_app_config():
    """
    Endpoint to get paged results of application configurations
    :return: list of app_config objects in json
    """
    page = request.args.get('page', 1, int)
    per_page = request.args.get('per_page', PER_PAGE, int)
    result = AppConfig.query.order_by(-AppConfig.id).paginate(page=page, per_page=per_page, count=True)
    response = {'items': [item.to_dict() for item in result.items], 'perPage': per_page, 'total': result.total}
    return Response(json.dumps(response), content_type='application/json'), 200


@admin.get('/api/configuration/')
def api_config():
    """
    :return: serialized app configuration
    """
    response = {
        'config': ConfigManager.serialize(),
        'labels': dict(ConfigManager.CONFIG_LABELS)
    }
    return json.dumps(response)


@admin.put('api/configuration/')
def api_config_write():
    """
    writes back app configurations & reloads the app
    :return: success or error if saving/writing fails
    """
    conf = request.json.get('conf')

    if ConfigManager.write_config(conf):
        return 'Configuration Saved Successfully', 200
    else:
        return 'Unable to Save Configuration', 417


@admin.get('/api/info/')
def api_info():
    """
    :return: serialized app information
    """
    response = {
        'version': current_app.config['CAESAR_VERSION']
    }
    return Response(json.dumps(response),
                    content_type='application/json'), 200


@admin.app_template_filter('to_config')
def to_config(items):
    output = [
        {"en": item, "tr": gettext(item)} for item in items
    ]
    return output

@admin.app_template_filter('get_data')
def get_data(table):
    if table == 'atob':
        items = AtobInfo.query.all()
        return [{"en": item.title, "tr": item.title_tr or ''} for item in items]

    if table == 'atoa':
        items = AtoaInfo.query.all()
        items_list = [
            {
                "en": {"text": item.title or '', "revtext": item.reverse_title or ''},
                "tr": {"text": item.title_tr or '', "revtext": item.reverse_title_tr or ''}
            } for item in items
        ]
        return items_list

    if table == 'itoa':
        items = ItoaInfo.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]

    if table == 'btob':
        items = BtobInfo.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]

    if table == 'itob':
        items = ItobInfo.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]

    if table == 'itoi':
        items = ItoiInfo.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]

    if table == 'otoo':
        items = OtooInfo.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]

    if table == 'otob':
        items = OtobInfo.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]

    if table == 'otoi':
        items = OtoiInfo.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]

    if table == 'workflow_status':
        items = WorkflowStatus.query.all()
        return [
            {"en": item.title, "tr": item.title_tr or ''}
            for item in items
        ]
