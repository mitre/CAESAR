from pathlib import Path

from flask import request, Response, json, send_from_directory
from flask.templating import render_template
from flask_security.decorators import auth_required, current_user, roles_required
from enferno.admin.models import Activity
from enferno.export.models import Export, GroupExport
from enferno.tasks import generate_export, generate_group_export
from enferno.utils.http_response import HTTPResponse
from apiflask import APIBlueprint

export = APIBlueprint('export', __name__, static_folder='../static',
                   template_folder='../export/templates', cli_group=None,
                   url_prefix='/export')

PER_PAGE = 30


@export.before_request
@auth_required('session')
def export_before_request():
    # check user's permissions
    if not (current_user.has_role("Admin") or current_user.can_export):
        return HTTPResponse.FORBIDDEN

@export.route('/dashboard/')
@export.get('/dashboard/<int:id>')
def exports_dashboard(id=None):
    """
    Endpoint to render the exports dashboard
    :return: html page of the exports dashbaord
    """
    return render_template('export-dashboard.html')

@export.post('/api/group/export')
def export_group():
    """
    creates a export request for a group of items
    :return: success code / failure if something goes wrong
    """
    export_request = GroupExport()
    export_request.from_json(request.json)
    if export_request.save():
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, export_request.to_mini(), GroupExport.__table__.name)
        return f'Export request created successfully, id:  {export_request.id} ', 200
    return 'Error creating export request', 417

@export.post('/api/bulletin/export')
def export_bulletins():
    """
    just creates an export request
    :return: success code / failure if something goes wrong
    """
    # create an export request
    export_request = Export()
    export_request.from_json('bulletin', request.json)
    if export_request.save():
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, export_request.to_mini(), Export.__table__.name)

        return f'Export request created successfully, id:  {export_request.id} ', 200
    return 'Error creating export request', 417

@export.post('/api/actor/export')
def export_actors():
    """
    just creates an export request
    :return: success code / failure if something goes wrong
    """
    # create an export request
    export_request = Export()
    export_request.from_json('actor', request.json)
    if export_request.save():
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, export_request.to_mini(), Export.__table__.name)
        return f'Export request created successfully, id:  {export_request.id} ', 200
    return 'Error creating export request', 417


@export.post('/api/incident/export')
def export_incidents():
    """
    just creates an export request
    :return: success code / failure if something goes wrong
    """
    # create an export request
    export_request = Export()
    export_request.from_json('incident', request.json)
    if export_request.save():
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, export_request.to_mini(), Export.__table__.name)
        return f'Export request created successfully, id:  {export_request.id} ', 200
    return 'Error creating export request', 417

@export.post('/api/organization/export')
def export_organizations():
    """
    just creates an export request
    :return: success code / failure if something goes wrong
    """
    # create an export request
    export_request = Export()
    export_request.from_json('organization', request.json)
    if export_request.save():
        # Record activity
        Activity.create(current_user, Activity.ACTION_CREATE, export_request.to_mini(), Export.__table__.name)
        return f'Export request created successfully, id:  {export_request.id} ', 200
    return 'Error creating export request', 417

@export.get('/api/export/<int:id>')
def api_export_get(id):
    """
    Endpoint to get a single export
    :param id: id of the export
    :return: export in json format / success or error
    """
    export = Export.query.get(id)

    if export is None:
        return HTTPResponse.NOT_FOUND
    else:
        return json.dumps(export.to_dict()), 200

@export.get('/api/group-export/<int:id>')
def api_group_export_get(id):
    """
    Endpoint to get a single group export
    :param id: id of the group export
    :return: group export in json format / success or error
    """
    group_export = GroupExport.query.get(id)

    if group_export is None:
        return HTTPResponse.NOT_FOUND
    else:
        return json.dumps(group_export.to_dict()), 200


@export.post('/api/exports/')
def api_exports():
    """
    API endpoint to feed export request items in josn format - supports paging
    and generated based on user role
    :param page: db query offset
    :return: successful json feed or error
    """
    page = request.json.get('page', 1)
    per_page = request.json.get('per_page', PER_PAGE)

    if current_user.has_role('Admin'):
        export_results = Export.query.order_by(-Export.id).all()
        group_export_results = GroupExport.query.order_by(-GroupExport.id).all()
    else:
        export_results = Export.query.filter(
            Export.requester_id == current_user.id
        ).order_by(-Export.id).all()
        group_export_results = GroupExport.query.filter(
            GroupExport.requester_id == current_user.id
        ).order_by(-GroupExport.id).all()

    # Combine and sort results
    combined_results = sorted(
        export_results + group_export_results,
        key=lambda x: x.updated_at,
        reverse=True
    )

    # Manual pagination
    total = len(combined_results)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_results = combined_results[start:end]

    response = {
        'items': [item.to_dict() for item in paginated_results],
        'perPage': per_page,
        'total': total
    }

    return Response(json.dumps(response), content_type='application/json')


@export.put('/api/group-exports/status')
@roles_required('Admin')
def change_group_export_status():
    """
    endpoint to approve or reject a group export request
    :return: success / error based on the operation outcome
    """
    if not request.json:
        return 'Invalid request', 417

    action = request.json.get('action')
    if not action or action not in ['approve', 'reject']:
        return 'Please check request action', 417

    export_id = request.json.get("exportId")

    if not export_id:
        return 'Invalid export request id', 417
    export_request = GroupExport.query.get(export_id)

    if not export_request:
        return 'Export request does not exist', 404

    if action == 'approve':
        export_request = export_request.approve()
        if export_request.save():
            # record activity
            Activity.create(current_user, Activity.ACTION_APPROVE_EXPORT, export_request.to_mini(), GroupExport.__table__.name)
            # implement celery task chaining
            res = generate_group_export(export_id)
            # not sure if there is a scenario where the result has no uuid
            # store export background task id, to be used for fetching progress
            export_request.uuid = res.id
            export_request.save()

            return 'Export request approval will be processed shortly.', 200

    if action == 'reject':
        export_request = export_request.reject()
        if export_request.save():
            # record activity
            Activity.create(current_user, Activity.ACTION_REJECT_EXPORT, export_request.to_mini(), GroupExport.__table__.name)

            return 'Export request rejected.', 200


@export.put('/api/exports/status')
@roles_required('Admin')
def change_export_status():
    """
    endpoint to approve or reject an export request
    :return: success / error based on the operation outcome
    """
    action = request.json.get('action')
    if not action or action not in ['approve', 'reject']:
        return 'Please check request action', 417
    export_id = request.json.get("exportId")

    if not export_id:
        return 'Invalid export request id', 417
    export_request = Export.query.get(export_id)

    if not export_request:
        return 'Export request does not exist', 404
    
    if action == 'approve':
        export_request = export_request.approve()
        if export_request.save():
            # record activity
            Activity.create(current_user, Activity.ACTION_APPROVE_EXPORT, export_request.to_mini(), Export.__table__.name)
            # implement celery task chaining
            res = generate_export(export_id)
            # not sure if there is a scenario where the result has no uuid
            # store export background task id, to be used for fetching progress
            export_request.uuid = res.id
            export_request.save()

            return 'Export request approval will be processed shortly.', 200

    if action == 'reject':
        export_request = export_request.reject()
        if export_request.save():
            # record activity
            Activity.create(current_user, Activity.ACTION_REJECT_EXPORT, export_request.to_mini(), Export.__table__.name)

            return 'Export request rejected.', 200


@export.put('/api/exports/expiry')
@roles_required('Admin')
def update_expiry():
    """
    endpoint to set expiry date of an approved export
    :return: success / error based on the operation outcome
    """
    export_id = request.json.get("exportId")
    new_date = request.json.get('expiry')
    export_request = Export.query.get(export_id)

    if export_request.expired:
        return HTTPResponse.FORBIDDEN
    else:
        try:
            export_request.set_expiry(new_date)
        except Exception as e:
            return 'Invalid expiry date', 417
        
        if export_request.save():
            return F"Updated Export #{export_id}", 200
        else:
            return 'Save failed', 417


@export.put('/api/group-exports/expiry')
@roles_required('Admin')
def update_group_expiry():
    """
    endpoint to set expiry date of an approved group export
    :return: success / error based on the operation outcome
    """
    export_id = request.json.get("exportId")
    new_date = request.json.get('expiry')
    export_request = GroupExport.query.get(export_id)

    if export_request.expired:
        return HTTPResponse.FORBIDDEN
    else:
        try:
            export_request.set_expiry(new_date)
        except Exception as e:
            return 'Invalid expiry date', 417

        if export_request.save():
            return F"Updated Group Export #{export_id}", 200
        else:
            return 'Save failed', 417


@export.get('/api/exports/download')
def download_export_file():
    """
    Endpoint to Download an export file
    :param export id identifier
    :return: url to download the file or access denied response if the export has expired
    """
    uid = request.args.get('exportId')

    try:

        export_id = Export.decrypt_unique_id(uid)
        export = Export.query.get(export_id)

        # check permissions for download
        # either admin or user is requester
        if not current_user.has_role('Admin'):
            if current_user.id != export.requester.id:
                return HTTPResponse.FORBIDDEN

        if not export_id or not export:
            return HTTPResponse.NOT_FOUND
        # check expiry
        if not export.expired:
            # Record activity
            Activity.create(current_user, Activity.ACTION_DOWNLOAD, export.to_mini(), Export.__table__.name)
            return send_from_directory(f'{Path(*Export.export_dir.parts[1:])}', f'{export.file_id}.zip')
        else:
            return HTTPResponse.REQUEST_EXPIRED

    except Exception as e:
        print(f'Unable to decrypt export request uid {e}')
        return HTTPResponse.NOT_FOUND


@export.get('/api/group-exports/download')
def download_group_export_file():
    """
    Endpoint to Download an group export file
    :param group export id identifier
    :return: url to download the file or access denied response if the group export has expired
    """
    uid = request.args.get('exportId')

    try:

        export_id = GroupExport.decrypt_unique_id(uid)
        export = GroupExport.query.get(export_id)

        # check permissions for download
        # either admin or user is requester
        if not current_user.has_role('Admin'):
            if current_user.id != export.requester.id:
                return HTTPResponse.FORBIDDEN

        if not export_id or not export:
            return HTTPResponse.NOT_FOUND
        # check expiry
        if not export.expired:
            # Record activity
            Activity.create(current_user, Activity.ACTION_DOWNLOAD, export.to_mini(), GroupExport.__table__.name)
            return send_from_directory(f'{Path(*GroupExport.export_dir.parts[1:])}', f'{export.file_id}.zip')
        else:
            return HTTPResponse.REQUEST_EXPIRED

    except Exception as e:
        print(f'Unable to decrypt group export request uid {e}')
        return HTTPResponse.NOT_FOUND
