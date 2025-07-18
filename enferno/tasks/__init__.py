# -*- coding: utf-8 -*-
import os
import shutil
import time
from collections import namedtuple
from datetime import datetime

import boto3
import pandas as pd
from celery import Celery, chain
from sqlalchemy import and_

from enferno.admin.models import Bulletin, Actor, Incident, BulletinHistory, Activity, ActorHistory, IncidentHistory, Organization, OrganizationHistory
from enferno.deduplication.models import DedupRelation
from enferno.export.models import Export, GroupExport
from enferno.extensions import db, rds
from enferno.settings import Config as cfg
from enferno.user.models import Role, User
from enferno.utils.csv_utils import convert_list_attributes
from enferno.data_import.models import DataImport
from enferno.data_import.utils.media_import import MediaImport
from enferno.data_import.utils.sheet_import import SheetImport
from enferno.utils.pdf_utils import PDFUtil

celery = Celery('tasks', broker=cfg.celery_broker_url)
# remove deprecated warning
celery.conf.update(
    {'accept_content': ['pickle', 'json', 'msgpack', 'yaml']})
celery.conf.update({'result_backend': os.environ.get('CELERY_RESULT_BACKEND', cfg.result_backend)})
celery.conf.update({'SQLALCHEMY_DATABASE_URI': os.environ.get('SQLALCHEMY_DATABASE_URI', cfg.SQLALCHEMY_DATABASE_URI)})
celery.conf.update({'SECRET_KEY': os.environ.get('SECRET_KEY', cfg.SECRET_KEY)})
celery.conf.add_defaults(cfg)


# Class to run tasks within application's context
class ContextTask(celery.Task):
    abstract = True
    def __call__(self, *args, **kwargs):
        from enferno.app import create_app
        with create_app(cfg).app_context():
            return super(ContextTask, self).__call__(*args, **kwargs)


celery.Task = ContextTask

# splitting db operations for performance
BULK_CHUNK_SIZE = 250


def chunk_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

@celery.task
def bulk_update_bulletins(ids, bulk, cur_user_id):
    print('processing bulletin bulk update')
    # build mappings
    u = {'id': cur_user_id}
    cur_user = namedtuple('cur_user', u.keys())(*u.values())
    user = User.query.get(cur_user_id)
    chunks = chunk_list(ids, BULK_CHUNK_SIZE)

    for group in chunks:

        # Fetch bulletins
        bulletins = Bulletin.query.filter(Bulletin.id.in_(group))
        for bulletin in bulletins:

            # check user can access each bulletin
            if not user.can_access(bulletin):
                # Log?
                continue

            # get Status initially
            status = bulk.get('status')

            # Assigned user
            assigned_to_id = bulk.get('assigned_to_id')
            if assigned_to_id:
                bulletin.assigned_to_id = assigned_to_id
                if not status:
                    bulletin.status = 'Assigned'

            # FPR user
            first_peer_reviewer_id = bulk.get('first_peer_reviewer_id')
            if first_peer_reviewer_id:
                bulletin.first_peer_reviewer_id = first_peer_reviewer_id
                if not status:
                    bulletin.status = 'Peer Review Assigned'

            if status:
                bulletin.status = status

            # Ref
            ref = bulk.get('ref')
            if ref:
                if bulk.get('refReplace') or not bulletin.ref:
                    bulletin.ref = ref
                else:
                    # merge refs / remove dups
                    bulletin.ref = list(set(bulletin.ref + ref))

            # Comment (required)
            bulletin.comments = bulk.get('comments', '')

            # Access Roles
            roles = bulk.get('roles')
            replace_roles = bulk.get('rolesReplace')
            if replace_roles:
                if roles:
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the bulletin
                    bulletin.roles = roles
                else:
                    # clear bulletin roles
                    bulletin.roles = []
            else:
                if roles:
                    # merge roles
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the bulletin
                    bulletin.roles = list(set(bulletin.roles + roles))

            # add only to session
            db.session.add(bulletin)

        print('creating revisions ...')
        revmaps = []
        bulletins = Bulletin.query.filter(Bulletin.id.in_(group)).all()
        for bulletin in bulletins:
            # this commits automatically
            tmp = {
                'bulletin_id': bulletin.id,
                'user_id': cur_user.id,
                'data': bulletin.to_dict()
            }
            revmaps.append(tmp)
        db.session.bulk_insert_mappings(BulletinHistory, revmaps)

        # commit session when a batch of items and revisions are added
        db.session.commit()

        # Record Activity
        updated = [b.to_mini() for b in bulletins]
        Activity.create(cur_user, Activity.ACTION_BULK_UPDATE, updated, 'bulletin')
        # perhaps allow a little time out
        time.sleep(.1)
        print('Chunk Processed')

    print("Bulletins Bulk Update Successful")


@celery.task
def bulk_update_actors(ids, bulk, cur_user_id):
    # build mappings
    u = {'id': cur_user_id}
    cur_user = namedtuple('cur_user', u.keys())(*u.values())
    user = User.query.get(cur_user_id)
    chunks = chunk_list(ids, BULK_CHUNK_SIZE)
    for group in chunks:

        # Fetch bulletins
        actors = Actor.query.filter(Actor.id.in_(group))
        for actor in actors:

            # check user can access each actor
            if not user.can_access(actor):
                # Log?
                continue

            # get Status initially
            status = bulk.get('status')

            # Assigned user
            assigned_to_id = bulk.get('assigned_to_id')
            if assigned_to_id:
                actor.assigned_to_id = assigned_to_id
                if not status:
                    actor.status = 'Assigned'

            # FPR user
            first_peer_reviewer_id = bulk.get('first_peer_reviewer_id')
            if first_peer_reviewer_id:
                actor.first_peer_reviewer_id = first_peer_reviewer_id
                if not status:
                    actor.status = 'Peer Review Assigned'

            if status:
                actor.status = status

            # Comment (required)
            actor.comments = bulk.get('comments', '')

            # Access Roles
            roles = bulk.get('roles')
            replace_roles = bulk.get('rolesReplace')
            if replace_roles:
                if roles:
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the bulletin
                    actor.roles = roles
                else:
                    # clear actor roles
                    actor.roles = []
            else:
                if roles:
                    # merge roles
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the actor
                    actor.roles = list(set(actor.roles + roles))

            # add only to session
            db.session.add(actor)

        revmaps = []
        actors = Actor.query.filter(Actor.id.in_(group)).all()
        for actor in actors:
            # this commits automatically
            tmp = {
                'actor_id': actor.id,
                'user_id': cur_user.id,
                'data': actor.to_dict()
            }
            revmaps.append(tmp)
        db.session.bulk_insert_mappings(ActorHistory, revmaps)

        # commit session when a batch of items and revisions are added
        db.session.commit()

        # Record Activity
        updated = [b.to_mini() for b in actors]
        Activity.create(cur_user, Activity.ACTION_BULK_UPDATE, updated, 'actor')
        # perhaps allow a little time out
        time.sleep(.25)
        print('Chunk Processed')

    print("Actors Bulk Update Successful")


@celery.task
def bulk_update_incidents(ids, bulk, cur_user_id):
    # build mappings
    u = {'id': cur_user_id}
    cur_user = namedtuple('cur_user', u.keys())(*u.values())
    user = User.query.get(cur_user_id)
    chunks = chunk_list(ids, BULK_CHUNK_SIZE)

    # for ops on related items
    assign_related = bulk.get('assignRelated')
    restrict_related = bulk.get('restrictRelated')
    actors = []
    bulletins = []

    for group in chunks:

        # Fetch bulletins
        incidents = Incident.query.filter(Incident.id.in_(group))
        for incident in incidents:

            # check if user can access incident
            if not user.can_access(incident):
                # Log?
                continue

            # get Status initially
            status = bulk.get('status')

            # Assigned user
            assigned_to_id = bulk.get('assigned_to_id')
            if assigned_to_id:
                incident.assigned_to_id = assigned_to_id
                if not status:
                    incident.status = 'Assigned'

            # FPR user
            first_peer_reviewer_id = bulk.get('first_peer_reviewer_id')
            if first_peer_reviewer_id:
                incident.first_peer_reviewer_id = first_peer_reviewer_id
                if not status:
                    incident.status = 'Peer Review Assigned'

            if status:
                incident.status = status

            # Comment (required)
            incident.comments = bulk.get('comments', '')

            # Access Roles
            roles = bulk.get('roles')
            replace_roles = bulk.get('rolesReplace')
            if replace_roles:
                if roles:
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the bulletin
                    incident.roles = roles
                else:
                    # clear incident roles
                    incident.roles = []
            else:
                if roles:
                    # merge roles
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the incident
                    incident.roles = list(set(incident.roles + roles))

            if assign_related or restrict_related:
                rel_actors = [itoa.actor_id for itoa in incident.related_actors]
                actors.extend(rel_actors)

                rel_bulletins = [itoa.bulletin_id for itoa in incident.related_bulletins]
                bulletins.extend(rel_bulletins)

            # add only to session
            db.session.add(incident)

        revmaps = []
        incidents = Incident.query.filter(Incident.id.in_(group)).all()
        for incident in incidents:
            # this commits automatically
            tmp = {
                'incident_id': incident.id,
                'user_id': cur_user.id,
                'data': incident.to_dict()
            }
            revmaps.append(tmp)
        db.session.bulk_insert_mappings(IncidentHistory, revmaps)

        # commit session when a batch of items and revisions are added
        db.session.commit()

        # Record Activity
        updated = [b.to_mini() for b in incidents]
        Activity.create(cur_user, Activity.ACTION_BULK_UPDATE, updated, 'incident')

        # restrict or assign related items
        if assign_related or restrict_related:
            # remove status
            bulk.pop('status', None)

            # not assigning related items
            if not assign_related:
                bulk.pop('assigned_to_id', None)
                bulk.pop('first_peer_reviewer_id', None)

            # not restricting related items
            if not restrict_related:
                bulk.pop('roles', None)
                bulk.pop('rolesReplace', None)

            # carry out bulk ops on related items
            if len(actors):
                bulk_update_actors(actors, bulk, cur_user_id)
            if len(bulletins):
                bulk_update_bulletins(bulletins, bulk, cur_user_id)

        # perhaps allow a little time out
        time.sleep(.25)
        print('Chunk Processed')

    print("Incidents Bulk Update Successful")

@celery.task
def bulk_update_organizations(ids, bulk, cur_user_id):
    # build mappings
    u = {'id': cur_user_id}
    cur_user = namedtuple('cur_user', u.keys())(*u.values())
    user = User.query.get(cur_user_id)
    chunks = chunk_list(ids, BULK_CHUNK_SIZE)

    for group in chunks:
        # Fetch organizations
        organizations = Organization.query.filter(Organization.id.in_(group))
        for organization in organizations:
            # check if user can access organization
            if not user.can_access(organization):
                # Log?
                continue

            # get Status initially
            status = bulk.get('status')

            # Assigned user
            assigned_to_id = bulk.get('assigned_to_id')
            if assigned_to_id:
                organization.assigned_to_id = assigned_to_id
                if not status:
                    organization.status = 'Assigned'

            # FPR user
            first_peer_reviewer_id = bulk.get('first_peer_reviewer_id')
            if first_peer_reviewer_id:
                organization.first_peer_reviewer_id = first_peer_reviewer_id
                if not status:
                    organization.status = 'Peer Review Assigned'

            if status:
                organization.status = status

            # Comment (required)
            organization.comments = bulk.get('comments', '')

            # Access Roles
            roles = bulk.get('roles')
            replace_roles = bulk.get('rolesReplace')
            if replace_roles:
                if roles:
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the organization
                    organization.roles = roles
                else:
                    # clear organization roles
                    organization.roles = []
            else:
                if roles:
                    # merge roles
                    role_ids = list(map(lambda x: x.get('id'), roles))
                    # get actual roles objects
                    roles = Role.query.filter(Role.id.in_(role_ids)).all()
                    # assign directly to the organization
                    organization.roles = list(set(organization.roles + roles))

            # add only to session
            db.session.add(organization)

        revmaps = []
        organizations = Organization.query.filter(Organization.id.in_(group)).all()
        for organization in organizations:
            # this commits automatically
            tmp = {
                'organization_id': organization.id,
                'user_id': cur_user.id,
                'data': organization.to_dict()
            }
            revmaps.append(tmp)
        db.session.bulk_insert_mappings(OrganizationHistory, revmaps)

        # commit session when a batch of items and revisions are added
        db.session.commit()

        # Record Activity
        updated = [o.to_mini() for o in organizations]
        Activity.create(cur_user, Activity.ACTION_BULK_UPDATE, updated, 'organization')
        # perhaps allow a little time out
        time.sleep(.1)
        print('Chunk Processed')

    print("Organizations Bulk Update Successful")

@celery.task(rate_limit=10)
def etl_process_file(batch_id, file, meta, user_id, data_import_id):
    try:
        di = MediaImport(batch_id, meta, user_id=user_id, data_import_id=data_import_id)
        di.process(file)
        return 'done'
    except Exception as e:
        log = DataImport.query.get(data_import_id)
        log.fail(e)

# this will publish a message to redis and will be captured by the front-end client
def update_stats():
    # send any message to refresh the UI
    # this will run only if the process is on
    rds.publish('dedprocess', 1)


@celery.task
def process_dedup(id, user_id):
    # print('processing {}'.format(id))
    d = DedupRelation.query.get(id)
    if d:
        d.process(user_id)
        # detect final task and send a refresh message
        if rds.scard('dedq') == 0:
            rds.publish('dedprocess', 2)

@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Deduplication periodic task
    if cfg.DEDUP_TOOL == True:
        seconds = int(os.environ.get('DEDUP_INTERVAL', cfg.DEDUP_INTERVAL))
        sender.add_periodic_task(seconds, dedup_cron.s(), name='Deduplication Cron')
        print("Deduplication periodic task is set up")
    # Export expiry periodic task
    if 'export' in db.metadata.tables.keys():
        sender.add_periodic_task(300, export_cleanup_cron.s(), name='Exports Cleanup Cron')
        print("Export cleanup periodic task is set up")


@celery.task
def dedup_cron():
    # shut down processing when we hit 0 items in the queue or when we turn off the processing
    if rds.get('dedup') != b'1' or rds.scard('dedq') == 0:
        rds.delete('dedup')
        rds.publish('dedprocess', 0)
        # Pause processing / do nothing
        print("Process engine - off")
        return

    data = []
    items = rds.spop('dedq', cfg.DEDUP_BATCH_SIZE).decode('utf-8')
    for item in items:
        data = item.split('|')
        process_dedup.delay(data[0], data[1])

    update_stats()

@celery.task
def process_row(filepath, sheet, row_id, data_import_id, map, batch_id, vmap, actor_config, lang, roles=[]):
    si = SheetImport(filepath, sheet, row_id, data_import_id, map, batch_id, vmap, roles, config=actor_config, lang=lang)
    si.import_row()

@celery.task
def reload_app():
    try:
        os.system('touch reload.ini')
        # this workaround will also restart local flask server if it is being used to run bayanat
        os.system('touch run.py')
    except Exception as e:
        print(e)

# ---- Export tasks ----
def generate_export(export_id):
    """
    Main Export generator task.
    """
    export_request = Export.query.get(export_id)

    if export_request.file_format == 'json':
        return chain(generate_json_file.s([export_id]),
                     generate_export_media.s(),
                     generate_export_zip.s())()

    elif export_request.file_format == 'pdf':
        return chain(generate_pdf_files.s([export_id]),
                     generate_export_media.s(),
                     generate_export_zip.s())()
    elif export_request.file_format == 'csv':
        return chain(generate_csv_file.s([export_id]),
                     generate_export_media.s(),
                     generate_export_zip.s())()

    elif export_request.file_format == 'csv':
        raise NotImplementedError


def generate_group_export(export_id):
    """
    Main Group Export generator task.
    """
    export_request = GroupExport.query.get(export_id)

    if export_request.file_format == 'json':
        return chain(generate_group_json_file.s([export_id]), generate_export_media.s([True]), generate_export_zip.s(['GroupExport']))()
    elif export_request.file_format == 'pdf':
        return chain(generate_group_pdf_files.s([export_id]),
                     generate_export_media.s([True]),
                     generate_export_zip.s(['GroupExport']))()
    elif export_request.file_format == 'csv':
        return chain(generate_group_csv_export.s([export_id]),
                     generate_export_media.s([True]),
                     generate_export_zip.s('GroupExport'))()

    elif export_request.file_format == 'csv':
        raise NotImplementedError


def clear_failed_export(export_request):
    shutil.rmtree(f'{Export.export_dir}/{export_request.file_id}')
    export_request.status = "Failed"
    export_request.file_id = None
    export_request.save()


@celery.task
def generate_pdf_files(export_id):
    """
    PDF export generator task.
    """
    export_request = Export.query.get(export_id)

    chunks = chunk_list(export_request.items, BULK_CHUNK_SIZE)
    dir_id = Export.generate_export_dir()
    try:
        for group in chunks:
            if export_request.table == 'bulletin':
                for bulletin in Bulletin.query.filter(Bulletin.id.in_(group)):
                    pdf = PDFUtil(bulletin)
                    pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')

            elif export_request.table == 'actor':
                for actor in Actor.query.filter(Actor.id.in_(group)):
                    pdf = PDFUtil(actor)
                    pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')

            elif export_request.table == 'incident':
                for incident in Incident.query.filter(Incident.id.in_(group)):
                    pdf = PDFUtil(incident)
                    pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')

            elif export_request.table == 'organization':
                for organization in Organization.query.filter(Organization.id.in_(group)):
                    pdf = PDFUtil(organization)
                    pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')

            time.sleep(0.2)

        export_request.file_id = dir_id
        export_request.save()
        print(f'---- Export generated successfully for Id: {export_request.id} ----')
        # pass the ids to the next celery task
        return export_id
    except Exception as e:
        print(f'Error writing export file: {e}')
        clear_failed_export(export_request)
        return False  # to stop chain


@celery.task
def generate_group_pdf_files(export_id):
    """
    PDF group export generator task.
    """
    export_request = GroupExport.query.get(export_id)

    chunks = chunk_list(export_request.items, BULK_CHUNK_SIZE)
    dir_id = GroupExport.generate_export_dir()
    try:
        for group in chunks:
            bulletin_group_items = [group_item.item_id for group_item in group if group_item.table == 'bulletin']
            actor_group_items = [group_item.item_id for group_item in group if group_item.table == 'actor']
            incident_group_items = [group_item.item_id for group_item in group if group_item.table == 'incident']
            organization_group_items = [group_item.item_id for group_item in group if group_item.table == 'org']
            for bulletin in Bulletin.query.filter(Bulletin.id.in_(bulletin_group_items)):
                pdf = PDFUtil(bulletin)
                pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')
            for actor in Actor.query.filter(Actor.id.in_(actor_group_items)):
                pdf = PDFUtil(actor)
                pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')
            for incident in Incident.query.filter(Incident.id.in_(incident_group_items)):
                pdf = PDFUtil(incident)
                pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')
            for organization in Organization.query.filter(Organization.id.in_(organization_group_items)):
                pdf = PDFUtil(organization)
                pdf.generate_pdf(f'{Export.export_dir}/{dir_id}/{pdf.filename}')
            time.sleep(0.2)

        export_request.file_id = dir_id
        export_request.save()
        print(f'---- Export generated successfully for Id: {export_request.id} ----')
        # pass the ids to the next celery task
        return export_id
    except Exception as e:
        print(f'Error writing export file: {e}')
        clear_failed_export(export_request)
        return False  # to stop chain


@celery.task
def generate_json_file(export_id: int):
    """
    JSON export generator task.
    """
    export_request = Export.query.get(export_id)
    chunks = chunk_list(export_request.items, BULK_CHUNK_SIZE)
    file_path, dir_id = Export.generate_export_file()
    export_type = export_request.table
    print('generating export file .....')
    try:
        with open(f'{file_path}.json', 'a') as file:
            file.write('{ \n')
            export_type_renamed = export_type
            if export_type == 'bulletin':
                export_type_renamed = 'primary_record'
            elif export_type == 'incident':
                export_type_renamed = 'investigation'
            file.write(f'"{export_type_renamed}s": [ \n')
            for group in chunks:
                if export_type == 'bulletin':
                    batch = ','.join(bulletin.to_json(export=True) for bulletin in Bulletin.query.filter(Bulletin.id.in_(group)))
                    file.write(f'{batch}\n')
                elif export_type == 'actor':
                    batch = ','.join(actor.to_json(export=True) for actor in Actor.query.filter(Actor.id.in_(group)))
                    file.write(f'{batch}\n')
                elif export_type == 'incident':
                    batch = ','.join(incident.to_json(export=True) for incident in Incident.query.filter(Incident.id.in_(group)))
                    file.write(f'{batch}\n')
                elif export_type == 'org':
                    batch = ','.join(organization.to_json(export=True) for organization in Organization.query.filter(Organization.id.in_(group)))
                    file.write(f'{batch}\n')
                # less db overhead
                time.sleep(0.2)
            file.write('] \n }')
        export_request.file_id = dir_id
        export_request.save()
        print(f'---- Export File generated successfully for Id: {export_request.id} ----')
        # pass the ids to the next celery task
        return export_id
    except Exception as e:
        print(f'Error writing export file: {e}')
        clear_failed_export(export_request)
        return False  # to stop chain


@celery.task
def generate_group_json_file(export_id: int):
    """
    JSON group export generator task.
    """
    export_request = GroupExport.query.get(export_id)
    bulletin_items = [item for item in export_request.items if item.table == 'bulletin']
    actor_items = [item for item in export_request.items if item.table == 'actor']
    incident_items = [item for item in export_request.items if item.table == 'incident']
    organization_items = [item for item in export_request.items if item.table == 'org']
    bulletin_chunks = chunk_list(bulletin_items, BULK_CHUNK_SIZE)
    actor_chunks = chunk_list(actor_items, BULK_CHUNK_SIZE)
    incident_chunks = chunk_list(incident_items, BULK_CHUNK_SIZE)
    organization_chunks = chunk_list(organization_items, BULK_CHUNK_SIZE)

    dir_id = GroupExport.generate_export_dir()
    def generate_item_file(ItemModel, item_name, item_chunks):
        file_name_renamed = item_name
        if item_name == 'bulletin':
            file_name_renamed = 'primary_record'
        elif item_name == 'incident':
            file_name_renamed = 'investigation'
        item_file_path = f'{Export.export_dir}/{dir_id}/{file_name_renamed}s'
        try:
            with open(f'{item_file_path}.json', 'a') as file:
                file.write('{ \n')
                key = item_name if item_name != 'bulletin' else 'primary_record'
                file.write(f'"{key}s": [ \n')
                for group in item_chunks:
                    batch = ','.join(item.to_json(export=True) for item in ItemModel.query.filter(ItemModel.id.in_([group_item.item_id for group_item in group])))
                    file.write(f'{batch}\n')
                    time.sleep(0.2)
                file.write('] \n }')

        except Exception as e:
            print(f'Error writing {item_name} export file: {e}')
            clear_failed_export(export_request)
            return False  # to stop chain
        return True

    if len(bulletin_items) > 0 and not generate_item_file(Bulletin, 'bulletin', bulletin_chunks):
        return False
    if len(actor_items) > 0 and not generate_item_file(Actor, 'actor', actor_chunks):
        return False
    if len(incident_items) > 0 and not generate_item_file(Incident, 'incident', incident_chunks):
        return False
    if len(organization_items) > 0 and not generate_item_file(Organization, 'organization', organization_chunks):
        return False

    export_request.file_id = dir_id
    export_request.save()
    print(f'---- Export File generated successfully for Id: {export_request.id} ----')
    # pass the ids to the next celery task
    return export_id

def convert_to_string(series_obj):
    """
    Converts the Dataframe series object to a string
    """
    if series_obj.item() != None:
        return series_obj.astype(str)
    return ''

@celery.task
def generate_csv_file(export_id: int):
    """
    CSV export generator task.
    """
    export_request = Export.query.get(export_id)
    file_path, dir_id = Export.generate_export_file()
    export_type = export_request.table
    print(file_path, dir_id)
    print('generating export file .....')
    try:
        csv_df = pd.DataFrame()
        for id in export_request.items:
            if export_type == 'bulletin':
                bulletin = Bulletin.query.get(id)
                # adjust list attributes to normal dicts
                adjusted = convert_list_attributes(bulletin.to_csv_dict())
                # normalize
                df = pd.json_normalize(adjusted)
                if csv_df.empty:
                    csv_df = df.apply(convert_to_string)
                else:
                    csv_df = pd.merge(csv_df, df.apply(convert_to_string), how='outer')

            elif export_type == 'actor':
                actor = Actor.query.get(id)
                # adjust list attributes to normal dicts
                adjusted = convert_list_attributes(actor.to_csv_dict())
                # normalize
                df = pd.json_normalize(adjusted)
                if csv_df.empty:
                    csv_df = df.apply(convert_to_string)
                else:
                    csv_df = pd.merge(csv_df, df.apply(convert_to_string), how='outer')

            elif export_type == 'org':
                organization = Organization.query.get(id)
                # adjust list attributes to normal dicts
                adjusted = convert_list_attributes(organization.to_csv_dict())
                # normalize
                df = pd.json_normalize(adjusted)
                if csv_df.empty:
                    csv_df = df.apply(convert_to_string)
                else:
                    csv_df = pd.merge(csv_df, df.apply(convert_to_string), how='outer')

        csv_df.to_csv(f'{file_path}.csv')

        export_request.file_id = dir_id
        export_request.save()
        print(f'---- Export File generated successfully for Id: {export_request.id} ----')
        # pass the ids to the next celery task
        return export_id
    except Exception as e:
        print(f'Error writing export file: {e}')
        clear_failed_export(export_request)
        return False  # to stop chain


@celery.task
def generate_group_csv_export(export_id: int):
    """
    CSV group export generator task.
    """
    export_request = GroupExport.query.get(export_id)
    dir_id = GroupExport.generate_export_dir()
    bulletin_csv_df = pd.DataFrame()
    actor_csv_df = pd.DataFrame()
    incident_csv_df = pd.DataFrame()
    organization_csv_df = pd.DataFrame()
    print('generating export file .....')
    for item in export_request.items:
        try:
            if item.table == 'bulletin':
                bulletin = Bulletin.query.get(item.item_id)
                adjusted = convert_list_attributes(bulletin.to_csv_dict())
                df = pd.json_normalize(adjusted)
                if bulletin_csv_df.empty:
                    bulletin_csv_df = df.apply(convert_to_string)
                else:
                    bulletin_csv_df = pd.merge(bulletin_csv_df, df.apply(convert_to_string), how='outer')
            elif item.table == 'actor':
                actor = Actor.query.get(item.item_id)
                adjusted = convert_list_attributes(actor.to_csv_dict())
                df = pd.json_normalize(adjusted)
                if actor_csv_df.empty:
                    actor_csv_df = df.apply(convert_to_string)
                else:
                    actor_csv_df = pd.merge(actor_csv_df, df.apply(convert_to_string), how='outer')
            elif item.table == 'org':
                organization = Organization.query.get(item.item_id)
                adjusted = convert_list_attributes(organization.to_csv_dict())
                df = pd.json_normalize(adjusted)
                if organization_csv_df.empty:
                    organization_csv_df = df.apply(convert_to_string)
                else:
                    organization_csv_df = pd.merge(organization_csv_df, df.apply(convert_to_string), how='outer')
        except Exception as e:
            print(f'Error writing export file: {e}')
            clear_failed_export(export_request)
            return False  # to stop chain

    if not bulletin_csv_df.empty:
        bulletin_csv_df.to_csv(f'{GroupExport.export_dir}/{dir_id}/primary_records.csv')
    if not actor_csv_df.empty:
        actor_csv_df.to_csv(f'{GroupExport.export_dir}/{dir_id}/actors.csv')
    if not incident_csv_df.empty:
        incident_csv_df.to_csv(f'{GroupExport.export_dir}/{dir_id}/investigations.csv')
    if not organization_csv_df.empty:
        organization_csv_df.to_csv(f'{GroupExport.export_dir}/{dir_id}/organizations.csv')

    export_request.file_id = dir_id
    export_request.save()
    print(f'---- Export File generated successfully for Id: {export_request.id} ----')
    # pass the ids to the next celery task
    return export_id


@celery.task
def generate_export_media(previous_result: int, is_group_export: bool = False):
    """
    Task to attach media files to export.
    """
    if previous_result == False:
        return False

    if is_group_export:
        export_request = GroupExport.query.get(previous_result)
    else:
        export_request = Export.query.get(previous_result)

    # check if we need to export media files
    if not export_request.include_media:
        return export_request.id

    if is_group_export:
        items = []
        bulletin_items = [item.item_id for item in export_request.items if item.table == 'bulletin']
        actor_items = [item.item_id for item in export_request.items if item.table == 'actor']
        items.extend(Bulletin.query.filter(Bulletin.id.in_(bulletin_items)))
        items.extend(Actor.query.filter(Actor.id.in_(actor_items)))
    else:
        export_type = export_request.table
        # get list of previous entity ids and export their medias
        # dynamic query based on table
        if export_type == 'bulletin':
            items = Bulletin.query.filter(Bulletin.id.in_(export_request.items))
        elif export_type == 'actor':
            items = Actor.query.filter(Actor.id.in_(export_request.items))
        else:
            # incidents and organizations have no media
            # UI switch disabled, but just in case...
            return

    for item in items:
        if item.medias:
            for media in item.medias:
                if media.shapefile_group_uuid:
                    os.makedirs(f'{Export.export_dir}/{export_request.file_id}/shapefiles/{media.shapefile_group_uuid}', exist_ok=True)
                    target_file = f'{Export.export_dir}/{export_request.file_id}/shapefiles/{media.shapefile_group_uuid}/{media.media_file}'
                else:
                    target_file = f'{Export.export_dir}/{export_request.file_id}/{media.media_file}'
                
                print(f'Exporting media file: {media.media_file}')

                if cfg.FILESYSTEM_LOCAL:
                    print('Downloading file locally')
                    if media.shapefile_group_uuid:
                        source_file = f'{media.media_dir}/shapefiles/{media.shapefile_group_uuid}/{media.media_file}'
                    else:
                        source_file = f'{media.media_dir}/{media.media_file}'
                    # copy file (including metadata)
                    shutil.copy2(source_file, target_file)
                else:
                    print('Downloading S3 file')
                    s3 = boto3.client('s3',
                                    aws_access_key_id=cfg.AWS_ACCESS_KEY_ID,
                                    aws_secret_access_key=cfg.AWS_SECRET_ACCESS_KEY,
                                    region_name=cfg.AWS_REGION
                                    )
                    try:
                        s3.download_file(cfg.S3_BUCKET, media.media_file, target_file)
                    except Exception as e:
                        print(f"Error downloading file from s3: {e}")

        time.sleep(0.05)
    return export_request.id


@celery.task
def generate_export_zip(previous_result: int, export_model='Export'):
    """
    Final export task to compress export folder
    into a zip archive.
    """
    ExportModel = Export if export_model == 'Export' else GroupExport

    if previous_result == False:
        return False

    print("Generating zip archive")
    export_request = ExportModel.query.get(previous_result)

    shutil.make_archive(f'{ExportModel.export_dir}/{export_request.file_id}', 'zip',
                        f'{ExportModel.export_dir}/{export_request.file_id}')
    print(f"Export Complete {export_request.file_id}.zip")

    # Remove export folder after completion
    shutil.rmtree(f'{ExportModel.export_dir}/{export_request.file_id}')

    # update request state
    export_request.status = 'Ready'
    export_request.save()


@celery.task
def export_cleanup_cron():
    """
    Periodic task to change status of
    expired Exports to 'Expired'.
    """
    expired_exports = Export.query.filter(and_(
        Export.expires_on < datetime.utcnow(),  # expiry time before now
        Export.status != 'Expired')).all()  # status is not expired

    if expired_exports:
        for export_request in expired_exports:
            export_request.status = 'Expired'
            if export_request.save():
                print(F"Expired Export #{export_request.id}")
                try:
                    os.remove(f'{Export.export_dir}/{export_request.file_id}.zip')
                except FileNotFoundError:
                    print(F"Export #{export_request.id}'s files not found to delete.")
            else:
                print(F"Error expiring Export #{export_request.id}")
