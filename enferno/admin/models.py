import json
import pathlib
from datetime import datetime
from functools import wraps
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from dateutil.parser import parse
from flask_babel import gettext
from flask_login import current_user
from geoalchemy2 import Geometry, Geography
from geoalchemy2.shape import to_shape
from shapely import centroid, to_geojson
from sqlalchemy import JSON, ARRAY, text, and_, or_, func, Enum
from sqlalchemy.dialects.postgresql import TSVECTOR, JSONB
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.utils import secure_filename
from enferno.admin.choices import Reliability, Sex

from enferno.extensions import db
from enferno.settings import Config as cfg
from enferno.user.models import Role
from enferno.utils.base import BaseMixin
from enferno.utils.csv_utils import convert_simple_relation, convert_complex_relation
from enferno.utils.date_helper import DateHelper
from enferno.utils.rename_utils import export_json_rename_handler

# Load configurations based on environment settings


######  Role based Access Control Decorator for Bulletins / Actors  / Incidents  ######
def check_roles(method):
    @wraps(method)
    def _impl(self, *method_args, **method_kwargs):
        method_output = method(self, *method_args, **method_kwargs)
        if current_user:
            if not current_user.can_access(self):
                return self.restricted_json()
        return method_output

    return _impl


def check_relation_roles(method):
    @wraps(method)
    def _impl(self, *method_args, **method_kwargs):
        method_output = method(self, *method_args, **method_kwargs)
        bulletin = method_output.get('bulletin')
        if bulletin and bulletin.get('restricted'):
            return {
                'bulletin': bulletin,
                'restricted': True
            }

        actor = method_output.get('actor')
        if actor and actor.get('restricted'):
            return {
                'actor': actor,
                'restricted': True
            }

        incident = method_output.get('incident')
        if incident and incident.get('restricted'):
            return {
                'incident': incident,
                'restricted': True
            }
        return method_output

    return _impl

def getCredibility(credibility):
    creds = {
        1: '1 - Confirmed',
        2: '2 - Probably True',
        3: '3 - Possibly True',
        4: '4 - Doubtful',
        5: '5 - Improbable',
        6: '6 - Truth cannot be judged'
    }

    return creds.get(credibility)

######  -----  ######

class ActorSubType(db.Model, BaseMixin):
    """
    SQL Alchemy model for Actor Sub Types
    """

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    actors = db.relationship("Actor", back_populates="sub_type")

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
        }

    def from_json(self, jsn):
        self.title = jsn.get('title')
        return self

class SanctionRegime(db.Model, BaseMixin):
    """
    SQL Alchemy model for Sanction Regimes
    """
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    sanction_regimes_to_actors = db.relationship("SanctionRegimeToActor", back_populates="sanction_regime", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
        }
    
    def from_json(self, jsn):
        self.title = jsn.get('title')
        return self
    
class SanctionRegimeToActor(db.Model, BaseMixin):
    """
    SQL Alchemy model for Sanction Regime to Actors
    Join table to match Actors to Sanction Regimes
    """
    id = db.Column(db.Integer, primary_key=True)
    
    sanction_regime_id = db.Column(db.Integer, db.ForeignKey('sanction_regime.id'))
    sanction_regime = db.relationship("SanctionRegime", back_populates="sanction_regimes_to_actors", foreign_keys=[sanction_regime_id])

    actor_id = db.Column(db.Integer, db.ForeignKey('actor.id'), nullable=True)
    actor = db.relationship("Actor", back_populates="sanction_regimes", foreign_keys=[actor_id])

    def to_dict(self):
        return {
            'id': self.id,
            'sanction_regime': self.sanction_regime.to_dict() if self.sanction_regime else None,
            'actor': self.actor.to_dict() if self.actor else None
        }
    
    def to_dict_actor(self):
        return {
            'id': self.id,
            'sanction_regime': self.sanction_regime.to_dict() if self.sanction_regime else None
        }
    
    def from_json(self, jsn):
        if jsn.get('sanction_regime_id'):
            self.sanction_regime_id = jsn.get('sanction_regime_id')
        elif jsn.get('sanction_regime'):
            self.sanction_regime_id = jsn.get('sanction_regime').get('id')
        if jsn.get('actor_id'):
            self.actor_id = jsn.get('actor_id')
        elif jsn.get('actor'):
            self.actor_id = jsn.get('actor').get('id')
        return self


class SocialMediaPlatform(db.Model, BaseMixin):
    """
    SQL Alchemy model for social media platforms
    """

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    handles = db.relationship("SocialMediaHandle", back_populates="platform", cascade="all, delete-orphan")
    handles_organization = db.relationship("SocialMediaHandleOrganization", back_populates="platform", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
        }

    def from_json(self, jsn):
        self.title = jsn.get('title')
        self.description = jsn.get('description')
        return self


class SocialMediaHandle(db.Model, BaseMixin):
    """
    SQL Alchemy model for social media handles
    """

    id = db.Column(db.Integer, primary_key=True)
    handle_name = db.Column(db.String, nullable=False)
    platform_id = db.Column(db.Integer, db.ForeignKey('social_media_platform.id'))
    platform = db.relationship("SocialMediaPlatform", back_populates="handles", foreign_keys=[platform_id])
    actor_id = db.Column(db.Integer, db.ForeignKey('actor.id'), nullable=True)
    actor = db.relationship("Actor", back_populates="social_media_handles", foreign_keys=[actor_id])

    def to_dict(self):
        return {
            'id': self.id,
            'handle_name': self.handle_name,
            'platform': self.platform.to_dict() if self.platform else None,
            'actor': self.actor.to_dict() if self.actor else None
        }

    def to_dict_actor(self):
        return {
            'id': self.id,
            'handle_name': self.handle_name,
            'platform': self.platform.to_dict() if self.platform else None
        }
    
    def from_json(self, jsn):
        self.handle_name = jsn.get('handle_name')
        if jsn.get('platform_id'):
            self.platform_id = jsn.get('platform_id')
        elif jsn.get('platform'):
            self.platform_id = jsn.get('platform').get('id')
        if jsn.get('actor_id'):
            self.actor_id = jsn.get('actor_id')
        return self

class SocialMediaHandleOrganization(db.Model, BaseMixin):
    """
    SQL Alchemy model for social media handles for organizations
    """

    id = db.Column(db.Integer, primary_key=True)
    handle_name = db.Column(db.String, nullable=False)
    platform_id = db.Column(db.Integer, db.ForeignKey('social_media_platform.id'))
    platform = db.relationship("SocialMediaPlatform", back_populates="handles_organization", foreign_keys=[platform_id])
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=True)
    organization = db.relationship("Organization", back_populates="social_media_handles", foreign_keys=[organization_id])

    def to_dict(self):
        return {
            'id': self.id,
            'handle_name': self.handle_name,
            'platform': self.platform.to_dict() if self.platform else None,
            'organization': self.organization.to_dict() if self.organization else None
        }

    def to_dict_organization(self):
        return {
            'id': self.id,
            'handle_name': self.handle_name,
            'platform': self.platform.to_dict() if self.platform else None
        }
    
    def from_json(self, jsn):
        self.handle_name = jsn.get('handle_name')
        if jsn.get('platform_id'):
            self.platform_id = jsn.get('platform_id')
        elif jsn.get('platform'):
            self.platform_id = jsn.get('platform').get('id')
        if jsn.get('organization_id'):
            self.organization_id = jsn.get('organization_id')
        return self

class ConsentUse(db.Model, BaseMixin):
    """
    SQL Alchemy model for consented uses
    """

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    consent_use_to_bulletins = db.relationship("ConsentUseToBulletin", back_populates="consent_use")

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
        }

    def from_json(self, jsn):
        self.title = jsn.get('title')
        return self

class ConsentUseToBulletin(db.Model, BaseMixin):
    """
    SQL Alchemy model for Consent Use to Bulletins
    Join table to match Consent Use to Bulletins
    """
    id = db.Column(db.Integer, primary_key=True)

    consent_use_id = db.Column(db.Integer, db.ForeignKey('consent_use.id'))
    consent_use = db.relationship("ConsentUse", back_populates="consent_use_to_bulletins", foreign_keys=[consent_use_id])

    bulletin_id = db.Column(db.Integer, db.ForeignKey('bulletin.id'), nullable=True)
    bulletin = db.relationship("Bulletin", back_populates="bulletin_to_consent_uses", foreign_keys=[bulletin_id])

    date = db.Column(db.DateTime)
    status = db.Column(db.String)

    def to_dict(self):
        return {
            'id': self.id,
            'consent_use': self.consent_use.to_dict() if self.consent_use else None,
            'bulletin': self.bulletin.to_dict() if self.bulletin else None
        }

    def to_dict_bulletin(self):
        return {
            'id': self.id,
            'consent_use': self.consent_use.to_dict() if self.consent_use else None,
            'date': DateHelper.serialize_datetime(self.date),
            'status': self.status
        }

    def from_json(self, jsn):
        if jsn.get('consent_use_id'):
            self.consent_use_id = jsn.get('consent_use_id')
        elif jsn.get('consent_use'):
            self.consent_use_id = jsn.get('consent_use').get('id')
        if jsn.get('bulletin_id'):
            self.bulletin_id = jsn.get('bulletin_id')
        elif jsn.get('bulletin'):
            self.bulletin_id = jsn.get('bulletin').get('id')
        if jsn.get('date'):
            self.date = DateHelper.parse_date(jsn.get('date'))
        if jsn.get('status'):
            self.status = jsn.get('status')
        return self


class Source(db.Model, BaseMixin):
    """
    SQL Alchemy model for sources
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    etl_id = db.Column(db.String, unique=True)
    title = db.Column(db.String, index=True)
    title_ar = db.Column(db.String, index=True)
    source_type = db.Column(db.String)
    comments = db.Column(db.Text)
    comments_ar = db.Column(db.Text)
    parent_id = db.Column(db.Integer, db.ForeignKey("source.id"), index=True)
    reliability = db.Column(Enum(Reliability))
    parent = db.relationship("Source", remote_side=id, backref="sub_source")

    # populate object from json dict
    def from_json(self, json):
        self.title = json["title"]
        if "title_ar" in json:
            self.title_ar = json["title_ar"]
        if "comments" in json:
            self.comments = json["comments"]
        if "comments_ar" in json:
            self.comments = json["comments_ar"]
        if "reliability" in json and json["reliability"]:
            if Reliability.is_valid(json["reliability"]):
                self.reliability = Reliability.get_name(json["reliability"])
            else:
                raise ValueError(f"{json['reliability']} is not a valid option for a source's reliability")

        parent = json.get('parent')
        if parent:
            self.parent_id = parent.get("id")
        else:
            self.parent_id = None
        return self

    # custom serialization method
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "etl_id": self.etl_id,
            "parent": {"id": self.parent.id, "title": self.parent.title} if self.parent else None,
            "comments": self.comments,
            "updated_at": DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None,
            "reliability": self.reliability.__str__() if self.reliability else None
        }

    def __repr__(self):
        return '<Source {} {}>'.format(self.id, self.title)

    def to_json(self):
        return json.dumps(self.to_dict())

    @staticmethod
    def find_by_ids(ids: list):
        """
        finds all items and subitems of a given list of ids, using raw sql query instead of the orm.
        :return: matching records
        """
        if not ids:
            return []
        qstr = tuple(ids)
        query = """
               with  recursive lcte (id, parent_id, title) as (
               select id, parent_id, title from source where id in :qstr union all 
               select x.id, x.parent_id, x.title from lcte c, source x where x.parent_id = c.id)
               select * from lcte;
               """
        result = db.engine.execute(text(query), qstr=qstr)

        return [{'id': x[0], 'title': x[2]} for x in result]

    @staticmethod
    def get_children(sources, depth=3):
        all = []
        targets = sources
        while depth != 0:
            children = Source.get_direct_children(targets)
            all += children
            targets = children
            depth -= 1
        return all

    @staticmethod
    def get_direct_children(sources):
        children = []
        for source in sources:
            children += source.sub_source
        return children

    @staticmethod
    def find_by_title(title):
        ar = Source.query.filter(Source.title_ar.ilike(title)).first()
        if ar:
            return ar
        else:
            return Source.query.filter(Source.title.ilike(title)).first()

    # import csv data into db
    @staticmethod
    def import_csv(file_storage):
        tmp = NamedTemporaryFile().name
        file_storage.save(tmp)
        df = pd.read_csv(tmp)
        df.comments = df.comments.fillna("")
        db.session.bulk_insert_mappings(Source, df.to_dict(orient="records"))
        db.session.commit()

        # reset id sequence counter
        max_id = db.session.execute("select max(id)+1  from source").scalar()
        db.session.execute(
            "alter sequence source_id_seq restart with :m", {'m': max_id})
        db.session.commit()
        print("Source ID counter updated.")

        return ""


class Label(db.Model, BaseMixin):
    """
    SQL Alchemy model for labels
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, index=True)
    title_ar = db.Column(db.String, index=True)
    comments = db.Column(db.String)
    comments_ar = db.Column(db.String)
    order = db.Column(db.Integer)
    verified = db.Column(db.Boolean, default=False)
    for_bulletin = db.Column(db.Boolean, default=False)
    for_actor = db.Column(db.Boolean, default=False)
    for_incident = db.Column(db.Boolean, default=False)
    for_offline = db.Column(db.Boolean, default=False)

    parent_label_id = db.Column(
        db.Integer, db.ForeignKey("label.id"), index=True, nullable=True
    )
    parent = db.relationship("Label", remote_side=id, backref="sub_label")

    # custom serialization method
    def to_dict(self, mode='1'):
        if mode == '2':
            return self.to_mode2()
        return {
            "id": self.id,
            "title": self.title,
            "title_ar": self.title_ar if self.title_ar else None,
            "comments": self.comments if self.comments else None,
            "comments_ar": self.comments_ar if self.comments_ar else None,
            "order": self.order,
            "verified": self.verified,
            "for_bulletin": self.for_bulletin,
            "for_actor": self.for_actor,
            "for_incident": self.for_incident,
            "for_offline": self.for_offline,
            "parent": {"id": self.parent.id, "title": self.parent.title}
            if self.parent else None,
            "updated_at": DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None
        }

    # custom compact serialization
    def to_mode2(self):
        return {
            "id": self.id,
            "title": self.title,
        }

    def to_json(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        return '<Label {} {}>'.format(self.id, self.title)

    @staticmethod
    def find_by_ids(ids: list):
        """
        finds all items and subitems of a given list of ids, using raw sql query instead of the orm.
        :return: matching records
        """
        if not ids:
            return []
        qstr = tuple(ids)

        query = """
                  with  recursive lcte (id, parent_label_id, title) as (
                  select id, parent_label_id, title from label where id in :qstr union all 
                  select x.id, x.parent_label_id, x.title from lcte c, label x where x.parent_label_id = c.id)
                  select * from lcte;
                  """
        result = db.engine.execute(text(query), qstr=qstr)

        return [{'id': x[0], 'title': x[2]} for x in result]

    @staticmethod
    def get_children(labels, depth=3):
        all = []
        targets = labels
        while depth != 0:
            children = Label.get_direct_children(targets)
            all += children
            targets = children
            depth -= 1
        return all

    @staticmethod
    def get_direct_children(labels):
        children = []
        for label in labels:
            children += label.sub_label
        return children

    @staticmethod
    def find_by_title(title):
        ar = Label.query.filter(Label.title_ar.ilike(title)).first()
        if ar:
            return ar
        else:
            return Label.query.filter(Label.title.ilike(title)).first()

    # populate object from json data
    def from_json(self, json):
        self.title = json["title"]
        self.title_ar = json["title_ar"] if "title_ar" in json else ""
        self.comments = json["comments"] if "comments" in json else ""
        self.comments_ar = json["comments_ar"] if "comments_ar" in json else ""
        self.verified = json.get("verified", False)
        self.for_bulletin = json.get("for_bulletin", False)
        self.for_actor = json.get("for_actor", False)
        self.for_incident = json.get("for_incident", False)
        self.for_offline = json.get("for_offline", False)

        parent_info = json.get('parent')
        if parent_info and 'id' in parent_info:
            parent_id = parent_info['id']
            if parent_id != self.id:
                p_label = Label.query.get(parent_id)
                # Check for circular relations
                if p_label and p_label.id != self.id and (not p_label.parent or p_label.parent.id != self.id):
                    self.parent_label_id = p_label.id
                else:
                    self.parent_label_id = None
            else:
                self.parent_label_id = None
        else:
            self.parent_label_id = None

        return self

    # import csv data into db
    @staticmethod
    def import_csv(file_storage):
        tmp = NamedTemporaryFile().name
        file_storage.save(tmp)
        df = pd.read_csv(tmp)
        # df.order.astype(int)
        df.sort_values(by=['id'])

        # first ignore foreign key constraints
        dfi = df.copy()
        del dfi['parent_label_id']

        #Make sure the id is unique and skip if title already exists
        current_id = db.session.execute("select max(id) from label").scalar()
        # if no labels exist then start from 1
        if current_id is None:
            current_id = 1
        else:
            current_id += 1
        added_labels = set()
        for i in range(len(dfi)):
            if dfi.loc[i]['title'] in added_labels:
                print("Label with title {} already added, skipping.".format(dfi.loc[i]['title']))
                dfi.drop(i, inplace=True)
                df.drop(i, inplace=True)
            elif Label.query.filter_by(title=dfi.loc[i]['title']).first():
                print("Label with title {} already exists, skipping.".format(dfi.loc[i]['title']))
                dfi.drop(i, inplace=True)
                df.drop(i, inplace=True)
            else:
                dfi.loc[i, 'id'] = current_id + i
                df.loc[i, 'id'] = current_id + i
                added_labels.add(dfi.loc[i]['title'])
        # first insert
        db.session.bulk_insert_mappings(Label, dfi.to_dict(orient="records"))

        # then drop labels with no foreign keys and update
        df = df[df['parent_label_id'].notna()]
        db.session.bulk_update_mappings(Label, df.to_dict(orient="records"))
        db.session.commit()

        # reset id sequence counter
        max_id = db.session.execute("select max(id)+1  from label").scalar()
        db.session.execute("alter sequence label_id_seq restart with :m", {'m': max_id})
        db.session.commit()
        print("Label ID counter updated.")
        return ""


class Eventtype(db.Model, BaseMixin):
    """
    SQL Alchemy model for event types
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String)
    title_ar = db.Column(db.String)
    for_actor = db.Column(db.Boolean, default=False)
    for_bulletin = db.Column(db.Boolean, default=False)
    comments = db.Column(db.String)

    # custom serialization method
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "title_ar": self.title_ar or None,
            "for_actor": self.for_actor,
            "for_bulletin": self.for_bulletin,
            "comments": self.comments,
            "updated_at": DateHelper.serialize_datetime(self.updated_at)

        }

    def to_json(self):
        return json.dumps(self.to_dict())

    # populates model from json dict
    def from_json(self, json):
        self.title = json.get("title", self.title)
        self.title_ar = json.get("title_ar", self.title_ar)
        self.for_actor = json.get("for_actor", self.for_actor)
        self.for_bulletin = json.get("for_bulletin", self.for_bulletin)
        self.comments = json.get("comments", self.comments)

        return self

    @staticmethod
    def find_by_title(title):
        # search
        return Eventtype.query.filter(Eventtype.title.ilike(title.strip())).first()

    # imports data from csv
    @staticmethod
    def import_csv(file_storage):
        tmp = NamedTemporaryFile().name
        file_storage.save(tmp)
        df = pd.read_csv(tmp)
        df.title_ar = df.title_ar.fillna("")
        df.comments = df.comments.fillna("")
        db.session.bulk_insert_mappings(Eventtype, df.to_dict(orient="records"))
        db.session.commit()

        # reset id sequence counter
        max_id = db.session.execute("select max(id)+1  from eventtype").scalar()
        db.session.execute(
            "alter sequence eventtype_id_seq restart with :m", {'m': max_id})
        db.session.commit()
        print("Eventtype ID counter updated.")
        return ""


class Event(db.Model, BaseMixin):
    """
    SQL Alchemy model for events
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, index=True)
    title_ar = db.Column(db.String, index=True)
    comments = db.Column(db.Text)
    comments_ar = db.Column(db.String)

    location_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    location = db.relationship(
        "Location", backref="location_events", foreign_keys=[location_id]
    ) 
    custom_location = db.Column(db.Boolean)
    geo_location_id = db.Column(db.Integer, db.ForeignKey("geo_location.id"))
    geo_location = db.relationship(
        "GeoLocation", backref="geo_location_events", foreign_keys=[geo_location_id]
    )
    
    eventtype_id = db.Column(db.Integer, db.ForeignKey("eventtype.id"))
    eventtype = db.relationship(
        "Eventtype", backref="eventtype_events", foreign_keys=[eventtype_id]
    )
    from_date = db.Column(db.Date)
    from_time = db.Column(db.Time)
    to_date = db.Column(db.Date)
    to_time = db.Column(db.Time)
    estimated = db.Column(db.Boolean)

    @staticmethod
    def get_event_filters(dates=None, eventtype_id=None, event_location_id=None):
        conditions = []

        if dates:
            start_date = parse(dates[0]).date()
            end_date = parse(dates[1]).date()

            date_condition = or_(
                and_(func.date(Event.from_date) <= start_date, func.date(Event.to_date) >= end_date),
                func.date(Event.from_date).between(start_date, end_date),
                func.date(Event.to_date).between(start_date, end_date)
            )
            conditions.append(date_condition)

        if event_location_id:
            conditions.append(Event.location_id == event_location_id)
        if eventtype_id:
            conditions.append(Event.eventtype_id == eventtype_id)

        return conditions

    # custom serialization method
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title if self.title else None,
            "title_ar": self.title_ar if self.title_ar else None,
            "comments": self.comments if self.comments else None,
            "comments_ar": self.comments_ar if self.comments_ar else None,
            "location": self.location.to_dict() if self.location else None,
            "geo_location": self.geo_location.to_dict() if self.geo_location else None,
            "custom_location": self.custom_location if self.custom_location else None,
            "eventtype": self.eventtype.to_dict() if self.eventtype else None,
            "from_date": DateHelper.serialize_date(self.from_date) if self.from_date else None,
            "from_time": DateHelper.serialize_time(self.from_time) if self.from_time else None,
            "to_date": DateHelper.serialize_date(self.to_date) if self.to_date else None,
            "to_time": DateHelper.serialize_time(self.to_time) if self.to_time else None,
            "estimated": self.estimated if self.estimated else None,
            "updated_at": DateHelper.serialize_datetime(self.updated_at)
        }

    def to_json(self):
        return json.dumps(self.to_dict())

    # populates model from json dict
    def from_json(self, json):
        self.title = json["title"] if "title" in json else None
        self.title_ar = json["title_ar"] if "title_ar" in json else None
        self.comments = json["comments"] if "comments" in json else None
        self.comments_ar = json["comments_ar"] if "comments_ar" in json else None
        
        self.custom_location = json["custom_location"] if "custom_location" in json else None
        if self.custom_location:
            if "geo_location" in json:
                geo_location = json["geo_location"]
                if geo_location is not None:
                    self.geo_location_id = geo_location.get("id", None)
                    self.custom_location = True
            else:
                self.geo_location_id = None   
            self.location = None    
            self.location_id = None
            
        else:
            if "location" in json:
                location = json["location"]
                if location is not None:
                    self.location_id = location.get("id", None)
                    self.custom_location = False
            else:
                self.location_id = None
            self.geo_location = None
            self.geo_location_id = None 
             
        # self.geo_location_id = json["geo_location"]["id"] if "geo_location" in json and json["geo_location"] else None
        self.eventtype_id = json["eventtype"]["id"] if "eventtype" in json and json["eventtype"] else None

        from_date = json.get('from_date', None)
        self.from_date = DateHelper.parse_date(from_date) if from_date else None

        self.from_time = json.get('from_time', None)
        if self.from_time == '':
            self.from_time = None

        to_date = json.get('to_date', None)
        self.to_date = DateHelper.parse_date(to_date) if to_date else None

        self.to_time = json.get('to_time', None)
        if self.to_time == '':
            self.to_time = None

        self.estimated = json["estimated"] if "estimated" in json else None

        return self


class Media(db.Model, BaseMixin):
    """
    SQL Alchemy model for media
    """
    __table_args__ = {"extend_existing": True}

    # set media directory here (could be set in the settings)
    media_dir = Path("enferno/media")
    inline_dir = Path("enferno/media/inline")
    id = db.Column(db.Integer, primary_key=True)
    media_file = db.Column(db.String, nullable=False)
    media_file_type = db.Column(db.String, nullable=False)
    category = db.Column(db.Integer)
    etag = db.Column(db.String, unique=True)
    duration = db.Column(db.String)

    title = db.Column(db.String)
    title_ar = db.Column(db.String)
    comments = db.Column(db.String)
    comments_ar = db.Column(db.String)
    search = db.Column(db.Text, db.Computed(
        '''
        ((((((((id::text || ' '::text) || COALESCE(title, ''::character varying)::text) || ' '::text)
         || COALESCE(media_file, ''::character varying)::text) || ' '::text) ||
          COALESCE(media_file_type, ''::character varying)::text) || ' '::text) || 
          COALESCE(comments, ''::character varying)::text) 
        '''
    ))

    time = db.Column(db.Float(precision=2))
    blur = db.Column(db.Boolean, default=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_medias", foreign_keys=[user_id])

    bulletin_id = db.Column(db.Integer, db.ForeignKey("bulletin.id"))
    bulletin = db.relationship("Bulletin", backref="medias", foreign_keys=[bulletin_id])

    actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"))
    actor = db.relationship("Actor", backref="medias", foreign_keys=[actor_id])

    main = db.Column(db.Boolean, default=False)
    
    # Not used by Bayanat, used by the data pipeline to indicate the record has been
    # synced to the Gold database
    ingested = db.Column(db.Boolean, default=False)

    # custom serialization method
    @check_roles
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title if self.title else None,
            "title_ar": self.title_ar if self.title_ar else None,
            "fileType": self.media_file_type if self.media_file_type else None,
            "filename": self.media_file if self.media_file else None,
            "etag": getattr(self, 'etag', None),
            "time": getattr(self, 'time', None),
            "blur": getattr(self, 'blur', None),
            "duration": self.duration,
            "main": self.main,
            "updated_at": DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None
        }

    def to_json(self):
        return json.dumps(self.to_dict())

    # populates model from json dict
    def from_json(self, json):
        self.title = json["title"] if "title" in json else None
        self.title_ar = json["title_ar"] if "title_ar" in json else None
        self.media_file_type = json["fileType"] if "fileType" in json else None
        self.media_file = json["filename"] if "filename" in json else None
        self.etag = json.get('etag', None)
        self.time = json.get('time', None)
        self.blur = json.get('blur', None)
        category = json.get('category', None)
        if category:
            self.category = category.get('id')
        return self

    # generate custom file name for upload purposes
    @staticmethod
    def generate_file_name(filename):
        return "{}-{}".format(
            datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
            secure_filename(filename).lower(),
        )

    @staticmethod
    def validate_media_extension(filename):
        return pathlib.Path(filename).suffix.lower() in cfg.MEDIA_ALLOWED_EXTENSIONS

    @staticmethod
    def validate_sheet_extension(filename):
        extension = pathlib.Path(filename).suffix.lstrip('.')
        return extension in cfg.SHEETS_ALLOWED_EXTENSIONS


# Structure is copied over from previous system
class Location(db.Model, BaseMixin):
    """
    SQL Alchemy model for locations
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    parent = db.relationship("Location", remote_side=id, backref="child_locations")
    title = db.Column(db.String)
    title_ar = db.Column(db.String)
    location_type_id = db.Column(db.Integer, db.ForeignKey('location_type.id'))
    location_type = db.relationship("LocationType", foreign_keys=[location_type_id])
    geometry = db.Column(Geometry('GEOMETRY', srid=4326))
    admin_level_id = db.Column(db.Integer, db.ForeignKey('location_admin_level.id'))
    admin_level = db.relationship("LocationAdminLevel", foreign_keys=[admin_level_id])
    description = db.Column(db.Text)
    postal_code = db.Column(db.String)

    # migrate to a froeign key
    country_id = db.Column(db.Integer, db.ForeignKey('countries.id'))
    country = db.relationship('Country', backref='locations')

    tags = db.Column(ARRAY(db.String))
    full_location = db.Column(db.String)
    id_tree = db.Column(db.String)

    def create_revision(self, user_id=None, created=None):
        if not user_id:
            user_id = getattr(current_user, 'id', 1)
        l = LocationHistory(
            location_id=self.id, data=self.to_dict(), user_id=user_id
        )
        if created:
            l.created_at = created
            l.updated_at = created
        l.save()

        print("Created Location revision")

    def get_children_ids(self):
        children = Location.query.with_entities(Location.id).filter(Location.id_tree.like(f'%[{self.id}]%')).all()
        # leaf children will return at least their id
        return [x[0] for x in children]

    @staticmethod
    def get_children_by_id(id: int):
        children = Location.query.with_entities(Location.id).filter(Location.id_tree.like(f'%[{id}]%')).all()
        # leaf children will return at least their id
        return [x[0] for x in children]

    @staticmethod
    def find_by_title(title):
        ar = Location.query.filter(Location.title_ar.ilike(title)).first()
        if ar:
            return ar
        else:
            return Location.query.filter(Location.title.ilike(title)).first()

    # custom serialization method
    def to_dict(self):
        if self.parent:
            if not self.parent.admin_level:
                print(self.parent, ' <-')

        return {
            "id": self.id,
            "title": self.title,
            "title_ar": self.title_ar,
            "description": self.description,
            "location_type": self.location_type.to_dict() if self.location_type else '',
            "admin_level": self.admin_level.to_dict() if self.admin_level else '',
            "geometry": json.loads(to_geojson(to_shape(self.geometry))) if self.geometry else None,
            "postal_code": self.postal_code,
            "country": self.country.to_dict() if self.country else None ,
            "parent": self.to_parent_dict(),
            "tags": self.tags or [],
            "full_location": self.full_location,
            "full_string": '{} | {}'.format(self.full_location or '', self.title_ar or ''),
            "updated_at": DateHelper.serialize_datetime(self.updated_at)
        }

    def to_dict_without_geometry(self):
        if self.parent:
            if not self.parent.admin_level:
                print(self.parent, ' <-')

        return {
            "id": self.id,
            "title": self.title,
            "title_ar": self.title_ar,
            "location_type": self.location_type.to_dict() if self.location_type else '',
            "admin_level": self.admin_level.to_dict() if self.admin_level else '',
            "parent": self.to_parent_dict(),
            "full_location": self.full_location,
            "full_string": '{} | {}'.format(self.full_location or '', self.title_ar or ''),
        }

    def to_parent_dict(self):
        if not self.parent:
            return None
        else:
            return {
                "id": self.parent_id,
                "title": self.parent.title,
                "full_string": '{} | {}'.format(self.parent.full_location or '', self.parent.title_ar or ''),
                "admin_level": self.parent.admin_level.to_dict() if self.parent.admin_level else ''
            }

    # custom compact serialization method
    def min_json(self):
        return {
            'id': self.id,
            'location_type': self.location_type.to_dict() if self.location_type else '',
            'full_string': '{} | {}'.format(self.full_location, self.title_ar)
        }

    def to_compact(self):
        return {
            "id": self.id,
            "title": self.title,
            "full_string": self.get_full_string(),
            "lat_centroid": centroid(to_shape(self.geometry)).y if self.geometry else None,
            "lng_centroid": centroid(to_shape(self.geometry)).x if self.geometry else None,
            "geometry_type": self.geometry.type if self.geometry else None,
        }

    def to_json(self):
        return json.dumps(self.to_dict())

    # populate model from json dict
    def from_json(self, jsn):
        self.title = jsn.get('title')
        self.title_ar = jsn.get('title_ar')
        self.description = jsn.get('description')
        if jsn.get('geometry'):
            self.geometry = func.ST_GeomFromGeoJSON(f"{jsn.get('geometry')}")
        else:
            self.geometry = None

        # little validation doesn't hurt
        allowed_location_types = [l.title for l in LocationType.query.all()]
        if jsn.get('location_type') and jsn.get('location_type').get('title') in allowed_location_types:
            self.location_type_id = jsn.get('location_type').get('id')
            self.location_type = LocationType.query.get(self.location_type_id)

            if self.location_type.title == "Administrative Location":
                self.admin_level_id = jsn.get('admin_level').get('id')
                self.admin_level = LocationAdminLevel.query.get(self.admin_level_id)
            else:
                self.admin_level_id = None
                self.admin_level = None
        else:
            self.location_type = None

        self.full_location = jsn.get('full_location')
        self.postal_code = jsn.get('postal_code')
        country = jsn.get('country')
        if country and (id := country.get('id')):
            self.country_id = id
        else:
            self.country_id = None
        self.tags = jsn.get('tags', [])
        parent = jsn.get('parent')
        if parent and parent.get('id'):
            self.parent_id = parent.get('id')
        else:
            self.parent_id = None

        return self

    # helper method
    def get_sub_locations(self):
        if not self.sub_location:
            return [self]
        else:
            locations = [self]
            for l in self.sub_location:
                locations += [l] + l.get_sub_locations()
            return locations

    # helper method to get full location hierarchy
    def get_full_string(self, descending=True):
        """
        Generates full string of location and parents.
        """

        pid = self.parent_id
        if not pid or self.admin_level is None:
            return self.title

        string = []
        string.append(self.title)
        counter = self.admin_level.code

        while True:
            if pid:
                parent = Location.query.get(pid)
                if parent:
                    if descending:
                        string.insert(0, parent.title)
                    else:
                        string.append(parent.title)
                    pid = parent.parent_id

            counter -= 1
            if counter == 0:
                break

        return ', '.join(string)

    def get_id_tree(self):
        """
        use common table expressions to generate the full tree of ids, this is very useful to reduce
        search complexity when using autocomplete locations
        :return:
        """
        query = """
        with recursive tree(id,depth) as (
        select id, title, parent_id from location where id = :id
        union all
        select p.id, p.title, p.parent_id from location p, tree t
        where p.id = t.parent_id
        )
        select * from tree;
        """
        result = db.engine.execute(text(query), id=self.id)
        return ' '.join(['[{}]'.format(loc[0]) for loc in result])

    @staticmethod
    def geo_query_location(target_point, radius_in_meters):
        """Geosearch via locations"""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)

        return func.ST_DWithin(
            func.cast(Location.geometry, Geography),
            func.cast(point, Geography),
            radius_in_meters)

    @staticmethod
    def rebuild_id_trees():
        for l in Location.query.all():
            print('Generating id tree for Location - {}'.format(l.id))
            l.id_tree = l.get_id_tree()
            l.save()

        print('ID tree generated successfuly for location table')

    # imports csv data that's been read into a pandas df
    @staticmethod
    def import_csv_from_dataframe(df):
        no_df = df.drop('parent_id', axis=1)
        no_df['deleted'] = no_df['deleted'].astype('bool')

        # pick only locations with parents
        df = df[df.parent_id.notnull()]

        # convert parent to int
        df['parent_id'] = df['parent_id'].astype('int')

        # limit data frame to only id/parent_id pairs
        df = df[['id', 'parent_id']]

        # step.1 import locations - no parents
        no_df.to_sql('location', con=db.engine, index=False, if_exists='append')
        print('locations imported successfully')

        # step.2 update locations - add parents
        db.session.bulk_update_mappings(Location, df.to_dict(orient="records"))
        db.session.commit()
        print('locations parents imported successfully')

        # reset id sequence counter
        max_id = db.session.execute("select max(id)+1  from location").scalar()
        db.session.execute("alter sequence location_id_seq restart with :m", {'m': max_id})
        db.session.commit()
        print("Location ID counter updated.")

        return ""

    # imports csv data into db
    @staticmethod
    def import_csv(file_storage):
        tmp = NamedTemporaryFile().name
        file_storage.save(tmp)
        df = pd.read_csv(tmp)
        return Location.import_csv_from_dataframe(df)        



class LocationAdminLevel(db.Model, BaseMixin):
    """
    SQL Alchemy model for location admin levels
    """
    __table_args__ = {"extend_existing": True}
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'title': self.title
        }

    def from_json(self, jsn):
        self.code = jsn.get('code')
        self.title = jsn.get('title')


class LocationType(db.Model, BaseMixin):
    """
    SQL Alchemy model for location types
    """
    __table_args__ = {"extend_existing": True}
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.String)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description
        }

    def from_json(self, jsn):
        self.title = jsn.get('title')
        self.description = jsn.get('description')


class GeoLocation(db.Model, BaseMixin):
    """
        SQL Alchemy model for Geo markers (improved location class)
    """
    __table_args__ = {"extend_existing": True}
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String)
    type_id = db.Column(db.Integer, db.ForeignKey('geo_location_types.id'))
    type = db.relationship("GeoLocationType", backref="geolocations")  # Added a relationship
    main = db.Column(db.Boolean)
    geometry = db.Column(Geometry('GEOMETRY', srid=4326))
    comment = db.Column(db.Text)
    # bulletin_id = db.Column(db.Integer, db.ForeignKey('bulletin.id'))
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"))

    def from_json(self, jsn):
        self.title = jsn.get('title')
        type = jsn.get('geoType')
        if type and (id := type.get('id')):
            self.type_id = id
        self.main = jsn.get('main')
        if jsn.get('geometry'):
            self.geometry = func.ST_GeomFromGeoJSON(f"{jsn.get('geometry')}")
        else:
            self.geometry = None
        self.comment = jsn.get('comment')
        return self

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'type': self.type.to_dict() if self.type else None,
            'main': self.main,
            "geometry": json.loads(to_geojson(to_shape(self.geometry))) if self.geometry else None,
            'comment': self.comment,
            'updated_at': DateHelper.serialize_datetime(self.updated_at),
        }


# joint table
bulletin_sources = db.Table(
    "bulletin_sources",
    db.Column("source_id", db.Integer, db.ForeignKey("source.id"), primary_key=True),
    db.Column(
        "bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True
    ),
)

# joint table
bulletin_locations = db.Table(
    "bulletin_locations",
    db.Column(
        "location_id", db.Integer, db.ForeignKey("location.id"), primary_key=True
    ),
    db.Column(
        "bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True
    ),
)

# joint table
bulletin_labels = db.Table(
    "bulletin_labels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column(
        "bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True
    ),
)

# joint table
bulletin_verlabels = db.Table(
    "bulletin_verlabels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column(
        "bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True
    ),
)

# joint table
bulletin_events = db.Table(
    "bulletin_events",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column(
        "bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True
    ),
)

# joint table
bulletin_roles = db.Table(
    "bulletin_roles",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column(
        "bulletin_id", db.Integer, db.ForeignKey("bulletin.id"), primary_key=True
    ),
)


class Btob(db.Model, BaseMixin):
    """
    Bulletin to bulletin relationship model
    """
    extend_existing = True

    # This constraint will make sure only one relationship exists across bulletins (and prevent self relation)
    __table_args__ = (db.CheckConstraint("bulletin_id < related_bulletin_id"),)

    # Source Bulletin
    # Available Backref: bulletin_from
    bulletin_id = db.Column(db.Integer, db.ForeignKey("bulletin.id"), primary_key=True)

    # Target Bulletin
    # Available Backref: bulletin_to
    related_bulletin_id = db.Column(
        db.Integer, db.ForeignKey("bulletin.id"), primary_key=True
    )

    # Relationship extra fields
    related_as = db.Column(ARRAY(db.Integer))
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_btobs", foreign_keys=[user_id])

    @property
    def relation_info(self):
        related_infos = BtobInfo.query.filter(BtobInfo.id.in_(self.related_as)).all() if self.related_as else []
        # Return the to_dict representation of each of them
        return [info.to_dict() for info in related_infos]

    # Check if two bulletins are related , if so return the relation, otherwise false
    @staticmethod
    def are_related(a_id, b_id):

        if a_id == b_id:
            return False

        # with our id constraint set, just check if there is relation from the lower id to the upper id
        f, t = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        relation = Btob.query.get((f, t))
        if relation:
            return relation
        else:
            return False

    # Give an id, get the other bulletin id (relating in or out)
    def get_other_id(self, id):
        if id in (self.bulletin_id, self.related_bulletin_id):
            return (
                self.bulletin_id
                if id == self.related_bulletin_id
                else self.related_bulletin_id
            )
        return None

    # Create and return a relation between two bulletins making sure the relation goes from the lower id to the upper id
    @staticmethod
    def relate(a, b):
        f, t = min(a.id, b.id), max(a.id, b.id)
        return Btob(bulletin_id=f, related_bulletin_id=t)

    @staticmethod
    def relate_by_id(a, b):
        f, t = min(a, b), max(a, b)
        return Btob(bulletin_id=f, related_bulletin_id=t)

    # Exclude the primary bulletin from output to get only the related/relating bulletin
    @check_relation_roles
    def to_dict(self, exclude=None):
        if not exclude:
            return {
                "bulletin_from": self.bulletin_from.to_compact(),
                "bulletin_to": self.bulletin_to.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }
        else:
            bulletin = self.bulletin_to if exclude == self.bulletin_from else self.bulletin_from

            return {
                "bulletin": bulletin.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }

    # this will update only relationship data
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class BtobInfo(db.Model, BaseMixin):
    """
    Btob Relation Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


# Actor to bulletin uni-direction relation
class Atob(db.Model, BaseMixin):
    """
    Actor to bulletin relationship model
    """
    extend_existing = True

    # Available Backref: bulletin
    bulletin_id = db.Column(db.Integer, db.ForeignKey("bulletin.id"), primary_key=True)

    # Available Backref: actor
    actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"), primary_key=True)

    # Relationship extra fields
    # enabling multiple relationship types
    related_as = db.Column(ARRAY(db.Integer))
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_atobs", foreign_keys=[user_id])

    # Exclude the primary bulletin from output to get only the related/relating bulletin
    @property
    def relation_info(self):
        # Query the AtobInfo table based on the related_as list
        related_infos = AtobInfo.query.filter(AtobInfo.id.in_(self.related_as)).all() if self.related_as else []
        # Return the to_dict representation of each of them
        return [info.to_dict() for info in related_infos]

    # custom serialization method
    def to_dict(self):

        return {
            "bulletin": self.bulletin.to_compact(),
            "actor": self.actor.to_compact(),
            "related_as": self.related_as or [],
            "probability": self.probability,
            "comment": self.comment,
            "user_id": self.user_id,
        }

    # this will update only relationship data
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class AtobInfo(db.Model, BaseMixin):
    """
    Atob Relation Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


class Atoa(db.Model, BaseMixin):
    """
    Actor to actor relationship model
    """
    extend_existing = True

    # This constraint will make sure only one relationship exists across bulletins (and prevent self relation)
    __table_args__ = (db.CheckConstraint("actor_id < related_actor_id"),)

    actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"), primary_key=True)
    related_actor_id = db.Column(
        db.Integer, db.ForeignKey("actor.id"), primary_key=True
    )

    # Relationship extra fields
    related_as = db.Column(db.Integer)
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_atoas", foreign_keys=[user_id])

    @property
    def relation_info(self):
        related_info = AtoaInfo.query.filter(AtoaInfo.id == self.related_as).first() if self.related_as else None
        # Return the to_dict representation of the related_info if it exists, or an empty dictionary if not
        return related_info.to_dict() if related_info else {}

    # helper method to check if two actors are related and returns the relationship
    @staticmethod
    def are_related(a_id, b_id):

        if a_id == b_id:
            return False

        # with our id constraint set, just check if there is relation from the lower id to the upper id
        f, t = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        relation = Atoa.query.get((f, t))
        if relation:
            return relation
        else:
            return False

    # given one actor id, this method will return the other related actor id
    def get_other_id(self, id):
        if id in (self.actor_id, self.related_actor_id):
            return (
                self.actor_id if id == self.related_actor_id else self.related_actor_id
            )
        return None

    # Create and return a relation between two actors making sure the relation goes from the lower id to the upper id
    # a = 12 b = 11
    @staticmethod
    def relate(a, b):
        f, t = min(a.id, b.id), max(a.id, b.id)

        return Atoa(actor_id=f, related_actor_id=t)

    # Exclude the primary actor from output to get only the related/relating actor

    # custom serialization method
    @check_relation_roles
    def to_dict(self, exclude=None):
        if not exclude:
            return {
                "actor_from": self.actor_from.to_compact(),
                "actor_to": self.actor_to.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }
        else:
            actor = self.actor_to if exclude == self.actor_from else self.actor_from
            return {
                "actor": actor.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }

    # this will update only relationship data
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self

    def from_etl(self, json):
        pass


class AtoaInfo(db.Model, BaseMixin):
    """
    Atoa Relation Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=False)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


class Bulletin(db.Model, BaseMixin):
    """
    SQL Alchemy model for bulletins
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255), nullable=False)
    title_ar = db.Column(db.String(255))

    sjac_title = db.Column(db.String(255))
    sjac_title_ar = db.Column(db.String(255))

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_bulletins", foreign_keys=[user_id])

    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    assigned_to = db.relationship(
        "User", backref="assigned_to_bulletins", foreign_keys=[assigned_to_id]
    )
    description = db.Column(db.Text)

    discovery_file_name = db.Column(db.String(255))

    credibility = db.Column(db.Integer)
    
    reliability_score = db.Column(db.Integer, default=0)

    first_peer_reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    second_peer_reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    bulletin_to_consent_uses = db.relationship("ConsentUseToBulletin", back_populates="bulletin")

    first_peer_reviewer = db.relationship(
        "User", backref="first_rev_bulletins", foreign_keys=[first_peer_reviewer_id]
    )
    second_peer_reviewer = db.relationship(
        "User", backref="second_rev_bulletins", foreign_keys=[second_peer_reviewer_id]
    )

    sources = db.relationship(
        "Source",
        secondary=bulletin_sources,
        backref=db.backref("bulletins", lazy="dynamic"),
    )
    locations = db.relationship(
        "Location",
        secondary=bulletin_locations,
        backref=db.backref("bulletins", lazy="dynamic"),
    )

    labels = db.relationship(
        "Label",
        secondary=bulletin_labels,
        backref=db.backref("bulletins", lazy="dynamic"),
    )

    ver_labels = db.relationship(
        "Label",
        secondary=bulletin_verlabels,
        backref=db.backref("verlabels_bulletins", lazy="dynamic"),
    )

    events = db.relationship(
        "Event",
        secondary=bulletin_events,
        backref=db.backref("bulletins", lazy="dynamic"),
        order_by="Event.from_date"
    )

    roles = db.relationship(
        "Role",
        secondary=bulletin_roles,
        backref=db.backref("bulletins", lazy="dynamic")
    )

    # Bulletins that this bulletin relate to ->
    bulletins_to = db.relationship(
        "Btob", backref="bulletin_from", foreign_keys="Btob.bulletin_id"
    )

    # Bulletins that relate to this <-
    bulletins_from = db.relationship(
        "Btob", backref="bulletin_to", foreign_keys="Btob.related_bulletin_id"
    )

    # Related Actors
    related_actors = db.relationship(
        "Atob", backref="bulletin", foreign_keys="Atob.bulletin_id"
    )

    # Related Incidents
    related_incidents = db.relationship(
        "Itob", backref="bulletin", foreign_keys="Itob.bulletin_id"
    )

    related_organizations = db.relationship(
        "Otob", backref="bulletin", foreign_keys="Otob.bulletin_id"
    )

    publish_date = db.Column(
        db.Date, index=True
    )
    publish_time = db.Column(
        db.Time, index=True
    )

    documentation_date = db.Column(
        db.DateTime, index=True
    )

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_by = db.relationship(
        "User", backref="create_by_bulletins", foreign_keys=[created_by_id]
    )

    status = db.Column(db.String(255))
    source_link = db.Column(db.String(255))
    
    sensitive_data = db.Column(db.Boolean, default=False)

    # ref field : used for etl tagging etc ..
    ref = db.Column(ARRAY(db.String))

    # extra fields used by etl etc ..
    originid = db.Column(db.String, index=True)
    comments = db.Column(db.Text)

    # review fields
    review = db.Column(db.Text)
    review_action = db.Column(db.String)

    # metadata
    meta = db.Column(JSONB)

    tsv = db.Column(TSVECTOR)

    search = db.Column(db.Text, db.Computed(
        '''
        (((((((((((((((((id)::text || ' '::text) || (COALESCE(title, ''::character varying))::text) || ' '::text) ||
                        (COALESCE(title_ar, ''::character varying))::text) || ' '::text) ||
                      COALESCE(description, ''::text)) || ' '::text) ||
                    (COALESCE(originid, ''::character varying))::text) || ' '::text) ||
                  (COALESCE(sjac_title, ''::character varying))::text) || ' '::text) ||
                (COALESCE(sjac_title_ar, ''::character varying))::text) || ' '::text) ||
                (COALESCE(source_link, ''::character varying))::text) || ' '::text) 
                ||  ' '::text) || COALESCE(comments, ''::text)
        '''
    ))

    __table_args__ = (
        db.Index('ix_bulletin_search', 'search', postgresql_using="gin", postgresql_ops={'search': 'gin_trgm_ops'}),
    )

    # custom method to create new revision in history table
    def create_revision(self, user_id=None, created=None):
        if not user_id:
            user_id = getattr(current_user, 'id', 1)
        b = BulletinHistory(
            bulletin_id=self.id, data=self.to_dict(), user_id=user_id
        )
        if created:
            b.created_at = created
            b.updated_at = created
        b.save()

        print("created bulletin revision")

    # helper property returns all bulletin relations
    @property
    def bulletin_relations(self):
        return self.bulletins_to + self.bulletins_from

    @property
    def bulletin_relations_dict(self):
        return [relation.to_dict(exclude=self) for relation in self.bulletin_relations]

    @property
    def actor_relations_dict(self):
        return [relation.to_dict() for relation in self.actor_relations]

    @property
    def incident_relations_dict(self):
        return [relation.to_dict() for relation in self.incident_relations]

    @property
    def organization_relations_dict(self):
        return [relation.to_dict() for relation in self.organization_relations]

    # helper property returns all actor relations
    @property
    def actor_relations(self):
        return self.related_actors

    # helper property returns all incident relations
    @property
    def incident_relations(self):
        return self.related_incidents

    @property
    def organization_relations(self):
        return self.related_organizations

    # populate object from json dict
    def from_json(self, json):

        self.originid = json["originid"] if "originid" in json else None
        self.title = json["title"] if "title" in json else None
        self.sjac_title = json["sjac_title"] if "sjac_title" in json else None

        self.title_ar = json["title_ar"] if "title_ar" in json else None
        self.sjac_title_ar = json["sjac_title_ar"] if "sjac_title_ar" in json else None

        # assigned to
        if "assigned_to" in json and json["assigned_to"] and "id" in json["assigned_to"]:
            self.assigned_to_id = json["assigned_to"]["id"]

        # created by
        if "created_by" in json and json["created_by"] and "id" in json["created_by"]:
            self.created_by_id = json["created_by"]["id"]

        # first_peer_reviewer
        if "first_peer_reviewer" in json:
            if json["first_peer_reviewer"]:
                if "id" in json["first_peer_reviewer"]:
                    self.first_peer_reviewer_id = json["first_peer_reviewer"]["id"]

        self.description = json["description"] if "description" in json else None
        self.comments = json["comments"] if "comments" in json else None
        self.source_link = json["source_link"] if "source_link" in json else None
        self.sensitive_data = json.get('sensitive_data', False)
        self.discovery_file_name = json["discovery_file_name"] if "discovery_file_name" in json else None
        self.credibility = json["credibility"] if "credibility" in json else None
        self.ref = json["ref"] if "ref" in json else []

        # Locations
        if "locations" in json:
            ids = [location["id"] for location in json["locations"]]
            locations = Location.query.filter(Location.id.in_(ids)).all()
            self.locations = locations

        #Consent uses
        if "bulletin_to_consent_uses" in json:
            new_consent_use_relations = []
            for bulletin_to_consent_use in json["bulletin_to_consent_uses"]:
                if "id" not in bulletin_to_consent_use:
                    consent_use_to_bulletin = ConsentUseToBulletin()
                    consent_use_to_bulletin = consent_use_to_bulletin.from_json(bulletin_to_consent_use)
                    consent_use_to_bulletin.save()
                else:
                    # sanction_regime_to_actor already exists, get a db instance and update it with new data
                    consent_use_to_bulletin = ConsentUseToBulletin.query.get(bulletin_to_consent_use["id"])
                    consent_use_to_bulletin.from_json(bulletin_to_consent_use)
                    consent_use_to_bulletin.save()
                new_consent_use_relations.append(consent_use_to_bulletin)
            # remove old relations
            for consent_use_to_bulletin in self.bulletin_to_consent_uses:
                if consent_use_to_bulletin not in new_consent_use_relations:
                    consent_use_to_bulletin.delete()
            self.bulletin_to_consent_uses = new_consent_use_relations

        # Sources
        if "sources" in json:
            ids = [source["id"] for source in json["sources"]]
            sources = Source.query.filter(Source.id.in_(ids)).all()
            self.sources = sources

        # Labels
        if "labels" in json:
            ids = [label["id"] for label in json["labels"]]
            labels = Label.query.filter(Label.id.in_(ids)).all()
            self.labels = labels

        # verified Labels
        if "verLabels" in json:
            ids = [label["id"] for label in json["verLabels"]]
            ver_labels = Label.query.filter(Label.id.in_(ids)).all()
            self.ver_labels = ver_labels

        # Events
        if "events" in json:
            new_events = []
            events = json["events"]

            for event in events:
                g = None
                #if event["geo_location"]:
                if "geo_location" in event and "custom_location" in event and event["custom_location"] is True:
                    geo_location = event["geo_location"]
                    
                    if "id" not in geo_location:
                        # new geolocation
                        g = GeoLocation()
                        g.from_json(geo_location)
                        g.save()
                    else:
                        # geolocation exists // update
                        g = GeoLocation.query.get(geo_location['id'])
                        g.from_json(geo_location)
                        g.save()
                
                    if "id" not in event:
                        # new event
                        e = Event()
                        e = e.from_json(event)
                        if g is not None:
                            e.geo_location = g
                        e.save()
                        new_events.append(e)
                    else:
                        # event already exists, get a db instnace and update it with new data
                        e = Event.query.get(event["id"])
                        e.from_json(event)
                        if g is not None:
                            e.geo_location = g
                        e.save()
                        new_events.append(e)
                else:
                    if "id" not in event:
                        # new event
                        e = Event()
                        e = e.from_json(event)
                        e.save()
                    else:
                        # event already exists, get a db instnace and update it with new data
                        e = Event.query.get(event["id"])
                        e.from_json(event)
                        e.save()
                    new_events.append(e)
                            
            self.events = new_events

        if "roles" in json:
            ids = [role["id"] for role in json["roles"]]
            roles = Role.query.filter(Role.id.in_(ids)).all()
            self.roles = roles

        # Related Media
        if "medias" in json:
            # untouchable main medias
            main = [m for m in self.medias if m.main is True]
            others = [m for m in self.medias if not m.main]
            to_keep_ids = [m.get('id') for m in json.get('medias') if m.get('id')]

            # handle removed medias
            to_be_deleted = [m for m in others if m.id not in to_keep_ids]

            others = [m for m in others if m.id in to_keep_ids]
            to_be_created = [m for m in json.get('medias') if not m.get('id')]

            new_medias = []
            # create new medias
            for media in to_be_created:
                m = Media()
                m = m.from_json(media)
                m.save()
                new_medias.append(m)

            self.medias = main + others + new_medias

            # mark removed media as deleted
            for media in to_be_deleted:
                media.deleted = True
                delete_comment = f'Removed from Bulletin #{self.id}'
                media.comments = media.comments + '\n' + delete_comment if media.comments else delete_comment
                media.save()

        # Related Bulletins (bulletin_relations)
        if "bulletin_relations" in json:
            # collect related bulletin ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["bulletin_relations"]:
                bulletin = Bulletin.query.get(relation["bulletin"]["id"])
                # Extra (check those bulletins exit)

                if bulletin:
                    rel_ids.append(bulletin.id)
                    # this will update/create the relationship (will flush to db)
                    self.relate_bulletin(bulletin, relation=relation)

                # Find out removed relations and remove them
            # just loop existing relations and remove if the destination bulletin no in the related ids

            for r in self.bulletin_relations:
                # get related bulletin (in or out)
                rid = r.get_other_id(self.id)
                if not (rid in rel_ids):
                    r.delete()

                    # ------- create revision on the other side of the relationship
                    Bulletin.query.get(rid).create_revision()

        # Related Actors (actors_relations)
        if "actor_relations" in json:
            # collect related bulletin ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["actor_relations"]:
                actor = Actor.query.get(relation["actor"]["id"])
                if actor:
                    rel_ids.append(actor.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_actor(actor, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination actor no in the related ids

            for r in self.actor_relations:
                # get related bulletin (in or out)
                if not (r.actor_id in rel_ids):
                    rel_actor = r.actor
                    r.delete()

                    # --revision relation
                    rel_actor.create_revision()

        # Related Incidents (incidents_relations)
        if "incident_relations" in json:
            # collect related incident ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["incident_relations"]:
                incident = Incident.query.get(relation["incident"]["id"])
                if incident:
                    rel_ids.append(incident.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_incident(incident, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination incident no in the related ids

            for r in self.incident_relations:
                # get related bulletin (in or out)
                if not (r.incident_id in rel_ids):
                    rel_incident = r.incident
                    r.delete()

                    # --revision relation
                    rel_incident.create_revision()

        if "organization_relations" in json:
            # collect related organization ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["organization_relations"]:
                organization = Organization.query.get(relation["organization"]["id"])
                if organization:
                    rel_ids.append(organization.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_organization(organization, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination organization is not in the related ids

            for r in self.organization_relations:
                # get related bulletin (in or out)
                if not (r.organization_id in rel_ids):
                    rel_organization = r.organization
                    r.delete()

                    # --revision relation
                    rel_organization.create_revision()

        self.publish_date = json.get('publish_date', None)
        if self.publish_date == '':
            self.publish_date = None
        self.publish_time = json.get('publish_time', None)
        if self.publish_time == '':
            self.publish_time = None
        self.documentation_date = json.get('documentation_date', None)
        if self.documentation_date == '':
            self.documentation_date = None
        if "comments" in json:
            self.comments = json["comments"]

        if "status" in json:
            self.status = json["status"]

        return self

    # Compact dict for relationships
    @check_roles
    def to_compact(self):
        # locations json
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.to_compact())

        # sources json
        sources_json = []
        if self.sources and len(self.sources):
            for source in self.sources:
                sources_json.append({"id": source.id, "title": source.title})

        return {
            "id": self.id,
            "title": self.title,
            "title_ar": self.title_ar,
            "sjac_title": self.sjac_title or None,
            "sjac_title_ar": self.sjac_title_ar or None,
            "originid": self.originid or None,
            "locations": locations_json,
            "sources": sources_json,
            "description": self.description or None,
            "source_link": self.source_link or None,
            "sensitive_data": getattr(self, 'sensitive_data', False),
            "discovery_file_name": self.discovery_file_name or None,
            "credibility": self.credibility or None,
            "publish_date": DateHelper.serialize_date(self.publish_date),
            "publish_time": DateHelper.serialize_time(self.publish_time) or None,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "comments": self.comments or "",
        }

    def to_csv_dict(self):

        output = {
            'id': self.id,
            'title': self.serialize_column('title'),
            'title_ar': self.serialize_column('title_ar'),
            'origin_id': self.serialize_column('originid'),
            'source_link': self.serialize_column('source_link'),
            'discovery_file_name': self.serialize_column('discovery_file_name'),
            'credibility': self.serialize_column('credibility'),
            'sjac_title': self.serialize_column('sjac_title'),
            'sjac_title_ar': self.serialize_column('sjac_title_ar'),
            'description': self.serialize_column('description'),
            'publish_date': self.serialize_column('publish_date'),
            'publish_time': self.serialize_column('publish_time'),
            'created_at': self.serialize_column('created_at'),
            'labels': convert_simple_relation(self.labels),
            'verified_labels': convert_simple_relation(self.ver_labels),
            'sources': convert_simple_relation(self.sources),
            'locations': convert_simple_relation(self.locations),
            'media': convert_simple_relation(self.medias),
            'events': convert_simple_relation(self.events),
            'related_primary_records': convert_complex_relation(self.bulletin_relations_dict, Bulletin.__tablename__),
            'related_actors': convert_complex_relation(self.actor_relations_dict, Actor.__tablename__),
            'related_investigations': convert_complex_relation(self.incident_relations_dict, Incident.__tablename__),
            'related_organizations': convert_complex_relation(self.organization_relations_dict, Organization.__tablename__),

        }
        return output

    # Helper method to handle logic of relating bulletins  (from bulletin)
    def relate_bulletin(self, bulletin, relation=None, create_revision=True):
        # if a new bulletin is being created, we must save it to get the id
        if not self.id:
            self.save()

        # Relationships are alwasy forced to go from the lower id to the bigger id (to prevent duplicates)
        # Enough to look up the relationship from the lower to the upper

        # reject self relation
        if self == bulletin:
            # Cant relate bulletin to itself
            return

        existing_relation = Btob.are_related(self.id, bulletin.id)

        if existing_relation:
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation (possible from or to the bulletin based on the id comparison)
            new_relation = Btob.relate(self, bulletin)

            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # ------- create revision on the other side of the relationship
            if create_revision:
                bulletin.create_revision()

    # Helper method to handle logic of relating incidents (from a bulletin)

    def relate_incident(self, incident, relation=None, create_revision=True):
        # if current bulletin is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (incident_id,bulletin_id)
        existing_relation = Itob.query.get((incident.id, self.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Itob(incident_id=incident.id, bulletin_id=self.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # --revision relation
            if create_revision:
                incident.create_revision()

    def relate_organization(self, organization, relation=None, create_revision=True):
        # if current bulletin is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (organization_id,bulletin_id)
        existing_relation = Otob.query.get((organization.id, self.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Otob(organization_id=organization.id, bulletin_id=self.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # --revision relation
            if create_revision:
                organization.create_revision()

    # helper method to relate actors
    def relate_actor(self, actor, relation=None, create_revision=True):
        # if current bulletin is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (bulletin_id,actor_id)
        existing_relation = Atob.query.get((self.id, actor.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Atob(bulletin_id=self.id, actor_id=actor.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # --revision relation
            if create_revision:
                actor.create_revision()

    # custom serialization method
    @check_roles
    def to_dict(self, mode=None):
        if mode == '2':
            return self.to_mode2()
        if mode == '1':
            return self.min_json()

        # locations json
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.to_compact())

        # sources json
        sources_json = []
        if self.sources and len(self.sources):
            for source in self.sources:
                sources_json.append({"id": source.id, "title": source.title})

        # labels json
        labels_json = []
        if self.labels and len(self.labels):
            for label in self.labels:
                labels_json.append({"id": label.id, "title": label.title})

        # verified labels json
        ver_labels_json = []
        if self.ver_labels and len(self.ver_labels):
            for vlabel in self.ver_labels:
                ver_labels_json.append({"id": vlabel.id, "title": vlabel.title})

        # events json
        events_json = []
        if self.events and len(self.events):

            for event in self.events:
                events_json.append(event.to_dict())

        # medias json
        medias_json = []
        if self.medias and len(self.medias):

            for media in self.medias:
                medias_json.append(media.to_dict())

        #consent uses json
        consent_uses_json = []
        if self.bulletin_to_consent_uses and len(self.bulletin_to_consent_uses):
            for consent_use_relation in self.bulletin_to_consent_uses:
                consent_uses_json.append(consent_use_relation.to_dict_bulletin())

        # Related bulletins json (actually the associated relationships)
        # - in this case the other bulletin carries the relationship
        bulletin_relations_dict = []
        actor_relations_dict = []
        incident_relations_dict = []
        organization_relations_dict = []

        if str(mode) != '3':
            for relation in self.bulletin_relations:
                bulletin_relations_dict.append(relation.to_dict(exclude=self))

            # Related actors json (actually the associated relationships)
            for relation in self.actor_relations:
                actor_relations_dict.append(relation.to_dict())

            # Related incidents json (actually the associated relationships)
            for relation in self.incident_relations:
                incident_relations_dict.append(relation.to_dict())

            # Related organizations json (actually the associated relationships)
            for relation in self.organization_relations:
                organization_relations_dict.append(relation.to_dict())

        return {
            "class": self.__tablename__,
            "id": self.id,
            "title": self.title,
            "title_ar": self.title_ar,
            "sjac_title": self.sjac_title or None,
            "sjac_title_ar": self.sjac_title_ar or None,
            "originid": self.originid or None,
            # assigned to
            "assigned_to": self.assigned_to.to_compact() if self.assigned_to else None,
            "created_by": self.created_by.to_compact() if self.created_by else None,
            # first peer reviewer
            "first_peer_reviewer": self.first_peer_reviewer.to_compact()
            if self.first_peer_reviewer_id
            else None,
            "locations": locations_json,
            "labels": labels_json,
            "verLabels": ver_labels_json,
            "sources": sources_json,
            "events": events_json,
            "medias": medias_json,
            "bulletin_to_consent_uses": consent_uses_json,
            "bulletin_relations": bulletin_relations_dict,
            "actor_relations": actor_relations_dict,
            "incident_relations": incident_relations_dict,
            "organization_relations": organization_relations_dict,
            "description": self.description or None,
            "comments": self.comments or None,
            "source_link": self.source_link or None,
            "sensitive_data": self.sensitive_data or None,
            "discovery_file_name": self.discovery_file_name or None,
            "credibility": self.credibility or None,
            "_credibility": getCredibility(self.credibility) if self.credibility else None,
            "ref": self.ref or None,
            "publish_date": DateHelper.serialize_date(self.publish_date),
            "publish_time": DateHelper.serialize_time(self.publish_time) or None,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "status": self.status,
            "review": self.review if self.review else None,
            "review_action": self.review_action if self.review_action else None,
            "updated_at": DateHelper.serialize_datetime(self.get_modified_date()),
            "roles": [role.to_dict() for role in self.roles] if self.roles else [],

        }

    # custom serialization mode
    def to_mode2(self):
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.to_compact())

        # sources json
        sources_json = []
        if self.sources and len(self.sources):
            for source in self.sources:
                sources_json.append({"id": source.id, "title": source.title})

        return {
            "class": "Bulletin",
            "id": self.id,
            "title": self.title,
            "title_ar": self.title_ar,
            "sjac_title": self.sjac_title or None,
            "sjac_title_ar": self.sjac_title_ar or None,
            "originid": self.originid or None,
            # assigned to
            "locations": locations_json,
            "sources": sources_json,
            "description": self.description or None,
            "comments": self.comments or None,
            "source_link": self.source_link or None,
            "discovery_file_name": self.discovery_file_name or None,
            "credibility": self.credibility or None,
            "publish_date": DateHelper.serialize_date(self.publish_date),
            "publish_time": DateHelper.serialize_time(self.publish_time) or None,
            "created_at": DateHelper.serialize_datetime(self.created_at),

        }

    def to_json(self, export=False):
        bulletin_to_dict = self.to_dict()
        if export:
            bulletin_to_dict = export_json_rename_handler(bulletin_to_dict)
        return json.dumps(bulletin_to_dict)

    @staticmethod
    def get_columns():
        columns = []
        for column in Bulletin.__table__.columns:
            columns.append(column.name)
        return columns

    @staticmethod
    def geo_query_location(target_point, radius_in_meters):
        """Geosearch via locations"""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)
        return Bulletin.id.in_(
            db.session.query(bulletin_locations.c.bulletin_id)
            .join(Location, bulletin_locations.c.location_id == Location.id)
            .filter(func.ST_DWithin(
                func.cast(Location.geometry, Geography),
                func.cast(point, Geography),
                radius_in_meters))
        )

    @staticmethod
    def geo_query_geo_location(target_point, radius_in_meters):
        """Geosearch via geolocations"""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)
        return Bulletin.id.in_(
            db.session.query(GeoLocation.bulletin_id)
            .filter(func.ST_DWithin(
                func.cast(GeoLocation.geometry, Geography),
                func.cast(point, Geography),
                radius_in_meters))
        )

    @staticmethod
    def geo_query_event_location(target_point, radius_in_meters):
        """Condition for association between bulletin and location via events."""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)

        conditions = []
        conditions.append(
            Bulletin.id.in_(
                db.session.query(bulletin_events.c.bulletin_id)
                .join(Event, bulletin_events.c.event_id == Event.id)
                .join(Location, Event.location_id == Location.id)
                .filter(func.ST_DWithin(
                    func.cast(Location.geometry, Geography),
                    func.cast(point, Geography),
                    radius_in_meters))))
        conditions.append(
            Bulletin.id.in_(
                db.session.query(bulletin_events.c.bulletin_id)
                .join(Event, bulletin_events.c.event_id == Event.id)
                .join(GeoLocation, Event.geo_location_id == GeoLocation.id)
                .filter(func.ST_DWithin(
                    func.cast(GeoLocation.geometry, Geography),
                    func.cast(point, Geography),
                    radius_in_meters))))
        return or_(*conditions)
        

    def get_modified_date(self):

        if self.history:
            return self.history[-1].updated_at
        else:
            return self.updated_at


# joint table
actor_sources = db.Table(
    "actor_sources",
    db.Column("source_id", db.Integer, db.ForeignKey("source.id"), primary_key=True),
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
)

# joint table
actor_labels = db.Table(
    "actor_labels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
)

# joint table
actor_verlabels = db.Table(
    "actor_verlabels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column(
        "actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True
    ),
)

# joint table
actor_events = db.Table(
    "actor_events",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column("actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True),
)

# joint table
actor_roles = db.Table(
    "actor_roles",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column(
        "actor_id", db.Integer, db.ForeignKey("actor.id"), primary_key=True
    ),
)

actor_countries = db.Table('actor_countries',
    db.Column('actor_id', db.Integer, db.ForeignKey('actor.id'), primary_key=True),
    db.Column('country_id', db.Integer, db.ForeignKey('countries.id'), primary_key=True)
)

actor_ethnographies = db.Table('actor_ethnographies',
    db.Column('actor_id', db.Integer, db.ForeignKey('actor.id'), primary_key=True),
    db.Column('ethnography_id', db.Integer, db.ForeignKey('ethnographies.id'), primary_key=True)
)

class OrganizationType(db.Model, BaseMixin):
    """
    SQL Alchemy model for organization types
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    organizations = db.relationship('Organization', back_populates='organization_type')

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        return self

class OrganizationRoleActor(db.Model, BaseMixin):
    """
    SQL Alchemy model for organization roles to actor map
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    currently_active = db.Column(db.Boolean, default=True)
    from_date = db.Column(db.Date)
    to_date = db.Column(db.Date)

    actor_id = db.Column(db.Integer, db.ForeignKey('actor.id'))
    actor = db.relationship('Actor', back_populates='organization_roles', foreign_keys=[actor_id])

    organization_role_id = db.Column(db.Integer, db.ForeignKey('organization_role.id'))
    organization_role = db.relationship('OrganizationRole', back_populates='actors', foreign_keys=[organization_role_id])

    def to_dict(self):
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_name": self.actor.name if self.actor else None,
            "currently_active": self.currently_active,
            "from_date": DateHelper.serialize_date(self.from_date),
            "to_date": DateHelper.serialize_date(self.to_date),
            "organization_role_id": self.organization_role_id
        }
    
    def from_json(self, jsn):
        self.actor_id = jsn.get('actor_id', self.actor_id)
        self.currently_active = jsn.get('currently_active', self.currently_active)
        self.from_date = jsn.get('from_date', self.from_date)
        self.to_date = jsn.get('to_date', self.to_date)
        self.organization_role_id = jsn.get('organization_role_id', self.organization_role_id)
        return self


class OrganizationRole(db.Model, BaseMixin):
    """
    SQL Alchemy model for organization roles
    """
    extend_existing = True

    __table_args__ = (db.CheckConstraint('id != reports_to_id', name='organization_role_no_self_relation'),)

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255))
    currently_active = db.Column(db.Boolean, default=True)
    from_date = db.Column(db.Date)
    to_date = db.Column(db.Date)

    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'))
    organization = db.relationship('Organization', back_populates='roles_within', foreign_keys=[organization_id])

    actors = db.relationship('OrganizationRoleActor', back_populates='organization_role', cascade='all, delete-orphan')

    reports_to_id = db.Column(db.Integer, db.ForeignKey('organization_role.id'), nullable=True)
    reports_to = db.relationship('OrganizationRole', back_populates='reportees', remote_side=[id])

    reportees = db.relationship('OrganizationRole', back_populates='reports_to')

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "currently_active": self.currently_active,
            "from_date": DateHelper.serialize_date(self.from_date),
            "to_date": DateHelper.serialize_date(self.to_date),
            "organization_id": self.organization_id,
            "reports_to_id": self.reports_to_id,
            "reports_to_title": self.reports_to.title if self.reports_to else None,
            "reportees": [r.to_dict() for r in self.reportees],
            "actors": [a.to_dict() for a in self.actors]
        }
    
    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.currently_active = jsn.get('currently_active', self.currently_active)
        self.from_date = jsn.get('from_date', self.from_date)
        self.to_date = jsn.get('to_date', self.to_date)
        self.organization_id = jsn.get('organization_id', self.organization_id)
        self.reports_to_id = jsn.get('reports_to_id', self.reports_to_id)
        if "actors" in jsn:
            new_actors = []
            for actor in jsn["actors"]:
                if "id" not in actor:
                    # new actor
                    a = OrganizationRoleActor()
                    a = a.from_json(actor)
                    a.save()
                else:
                    # actor already exists, get a db instance and update it with new data
                    a = OrganizationRoleActor.query.get(actor["id"])
                    a.from_json(actor)
                    a.save()
                new_actors.append(a)
            # remove old actors
            for actor in self.actors:
                if actor not in new_actors:
                    actor.delete()
            self.actors = new_actors
        return self


class OrganizationAlias(db.Model, BaseMixin):
    """
    SQL Alchemy model for organization aliases
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    name_ar = db.Column(db.String, nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    organization = db.relationship('Organization', back_populates='aliases')

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "name_ar": self.name_ar,
            "organization_id": self.organization_id
        }

    def from_json(self, jsn):
        self.name = jsn['name'] if 'name' in jsn else self.name
        self.name_ar = jsn['name_ar'] if 'name_ar' in jsn else self.name_ar
        if 'organization_id' in jsn:
            self.organization_id = jsn['organization_id']
        elif 'organization' in jsn:
            self.organization_id = jsn['organization']['id']
        return self


organization_locations = db.Table('organization_locations',
                                  db.Column('organization_id', db.Integer, db.ForeignKey('organization.id'), primary_key=True),
                                  db.Column('location_id', db.Integer, db.ForeignKey('location.id'), primary_key=True)
                                  )

organization_events = db.Table(
    "organization_events",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column("organization_id", db.Integer, db.ForeignKey("organization.id"), primary_key=True),
)
# This is for ACCESS ROLES, different from the organization roles that relate to actors
organization_roles = db.Table('organization_roles',
                              db.Column('organization_id', db.Integer, db.ForeignKey('organization.id'), primary_key=True),
                              db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
                              )

class Organization(db.Model, BaseMixin):
    """
    SQL Alchemy model for organizations
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255))
    name_ar = db.Column(db.String(255))

    founded_date = db.Column(db.Date)
    description = db.Column(db.Text)
    status = db.Column(db.String(255))
    comments = db.Column(db.Text)

    organization_type_id = db.Column(db.Integer, db.ForeignKey('organization_type.id'), nullable=True)
    organization_type = db.relationship('OrganizationType', back_populates='organizations', foreign_keys=[organization_type_id])

    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_by = db.relationship('User', back_populates='created_organizations', foreign_keys=[created_by_id])

    first_peer_reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    first_peer_reviewer = db.relationship('User', back_populates='first_peer_reviewer_organizations', foreign_keys=[first_peer_reviewer_id])

    aliases = db.relationship('OrganizationAlias', back_populates='organization', cascade='all, delete-orphan')
    roles_within = db.relationship('OrganizationRole', back_populates='organization', cascade='all, delete-orphan')

    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_to = db.relationship("User", back_populates="assigned_to_organizations", foreign_keys=[assigned_to_id])

    social_media_handles = db.relationship('SocialMediaHandleOrganization', back_populates='organization')

    locations = db.relationship('Location',
                                secondary=organization_locations,
                                backref=db.backref('organizations', lazy='dynamic')
                                )

    events = db.relationship(
        "Event",
        secondary=organization_events,
        backref=db.backref("organization", lazy="dynamic"),
        order_by="Event.from_date"
    )

    roles = db.relationship('Role',
                            secondary=organization_roles,
                            backref=db.backref('organizations', lazy='dynamic')
                            )

    organizations_to = db.relationship(
        "Otoo", backref="organization_from", foreign_keys="Otoo.organization_id"
    )

    organizations_from = db.relationship(
        "Otoo", backref="organization_to", foreign_keys="Otoo.related_organization_id"
    )

    related_incidents = db.relationship(
        "Otoi", backref="organization", foreign_keys="Otoi.organization_id"
    )
    related_actors = db.relationship(
        "Otoa", backref="organization", foreign_keys="Otoa.organization_id"
    )
    related_bulletins = db.relationship(
        "Otob", backref="organization", foreign_keys="Otob.organization_id"
    )

    # review fields
    review = db.Column(db.Text)
    review_action = db.Column(db.String)

    # metadata
    meta = db.Column(JSONB)

    tsv = db.Column(TSVECTOR)

    search = db.Column(db.Text, db.Computed("""
         (id)::text || ' ' ||
         COALESCE(name, ''::character varying) || ' ' ||
         COALESCE(name_ar, ''::character varying) || ' ' ||
         COALESCE(description, ''::text) || ' ' ||
         COALESCE(comments, ''::text)
        """))

    __table_args__ = (
        db.Index('ix_organization_search', 'search', postgresql_using="gin", postgresql_ops={'search': 'gin_trgm_ops'}),
    )

    # custom method to create new revision in history table
    def create_revision(self, user_id=None, created=None):
        if not user_id:
            user_id = getattr(current_user, 'id', 1)
        b = OrganizationHistory(
            organization_id=self.id, data=self.to_dict(), user_id=user_id
        )
        if created:
            b.created_at = created
            b.updated_at = created
        b.save()

        print("created organization revision")

    # helper property returns all organization relations
    @property
    def organization_relations(self):
        return self.organizations_to + self.organizations_from

    @property
    def organization_relations_dict(self):
        return [relation.to_dict(exclude=self) for relation in self.organization_relations]

    # helper property returns all incident relations
    @property
    def incident_relations(self):
        return self.related_incidents

    @property
    def incident_relations_dict(self):
        return [relation.to_dict() for relation in self.incident_relations]

    @property
    def bulletin_relations(self):
        return self.related_bulletins

    @property
    def bulletin_relations_dict(self):
        return [relation.to_dict() for relation in self.bulletin_relations]

    @property
    def actor_relations(self):
        return self.related_actors

    @property
    def actor_relations_dict(self):
        return [relation.to_dict() for relation in self.actor_relations]

    def from_json(self, json):

        self.name = json["name"] if "name" in json else None
        self.name_ar = json["name_ar"] if "name_ar" in json else None
        self.founded_date = json["founded_date"] if "founded_date" in json else None
        self.description = json["description"] if "description" in json else None

        # assigned to
        if "assigned_to" in json and json["assigned_to"] and "id" in json["assigned_to"]:
            self.assigned_to_id = json["assigned_to"]["id"]

        # created by
        if "created_by" in json and json["created_by"] and "id" in json["created_by"]:
            self.created_by_id = json["created_by"]["id"]

        # first_peer_reviewer
        if "first_peer_reviewer" in json:
            if json["first_peer_reviewer"]:
                if "id" in json["first_peer_reviewer"]:
                    self.first_peer_reviewer_id = json["first_peer_reviewer"]["id"]

        if "organization_type" in json and json["organization_type"] and "id" in json["organization_type"]:
            self.organization_type_id = json["organization_type"]["id"]
        else:
            self.organization_type_id = None

        # Locations
        if "locations" in json:
            ids = [location["id"] for location in json["locations"]]
            locations = Location.query.filter(Location.id.in_(ids)).all()
            self.locations = locations

        if "roles" in json:
            ids = [role["id"] for role in json["roles"]]
            roles = Role.query.filter(Role.id.in_(ids)).all()
            self.roles = roles

        #aliases
        if "aliases" in json:
            new_aliases = []
            aliases = json["aliases"]
            for alias in aliases:
                if "id" not in alias:
                    # new alias
                    a = OrganizationAlias()
                    a = a.from_json(alias)
                    a.save()
                else:
                    # alias already exists, get a db instance and update it with new data
                    a = OrganizationAlias.query.get(alias["id"])
                    a.from_json(alias)
                    a.save()
                new_aliases.append(a)
            self.aliases = new_aliases

        # Events
        if "events" in json:
            new_events = []
            events = json["events"]
            for event in events:
                if "id" not in event:
                    # new event
                    e = Event()
                    e = e.from_json(event)
                    e.save()
                else:
                    # event already exists, get a db instance and update it with new data
                    e = Event.query.get(event["id"])
                    e.from_json(event)
                    e.save()
                new_events.append(e)
            self.events = new_events

        # Organization Roles Within
        if "roles_within" in json:
            new_roles = []
            roles_within = json["roles_within"]
            for role in roles_within:
                if "id" not in role:
                    # new role
                    r = OrganizationRole()
                    r = r.from_json(role)
                    r.save()
                else:
                    # role already exists, get a db instance and update it with new data
                    r = OrganizationRole.query.get(role["id"])
                    r.from_json(role)
                    r.save()
                new_roles.append(r)
            self.roles_within = new_roles

        # Social Media Handles
        if "social_media_handles" in json:
            new_handles = []
            handles = json["social_media_handles"]
            for handle in handles:
                if "id" not in handle:
                    # new handle
                    h = SocialMediaHandleOrganization()
                    h = h.from_json(handle)
                    h.save()
                else:
                    # handle already exists, get a db instance and update it with new data
                    h = SocialMediaHandleOrganization.query.get(handle["id"])
                    h.from_json(handle)
                    h.save()
                new_handles.append(h)
            self.social_media_handles = new_handles

        # Related Organizations (organization)
        if "organization_relations" in json:
            # collect related organization ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["organization_relations"]:
                organization = Organization.query.get(relation["organization"]["id"])
                # Extra (check those organization exit)

                if organization:
                    rel_ids.append(organization.id)
                    # this will update/create the relationship (will flush to db)
                    self.relate_organization(organization, relation=relation)

                # Find out removed relations and remove them
            # just loop existing relations and remove if the destination organization is not in the related ids

            for r in self.organization_relations:
                # get related organization (in or out)
                rid = r.get_other_id(self.id)
                if not (rid in rel_ids):
                    r.delete()

                    # ------- create revision on the other side of the relationship
                    Organization.query.get(rid).create_revision()

        # Related Bulletins (bulletin_relations)
        if "bulletin_relations" in json:
            # collect related bulletin ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["bulletin_relations"]:
                bulletin = Bulletin.query.get(relation["bulletin"]["id"])
                if bulletin:
                    rel_ids.append(bulletin.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_bulletin(bulletin, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination bulletin no in the related ids

            for r in self.bulletin_relations:
                # get related bulletin (in or out)
                if not (r.bulletin_id in rel_ids):
                    rel_bulletin = r.bulletin
                    r.delete()

                    # --revision relation
                    rel_bulletin.create_revision()

        # Related Incidents (incidents_relations)
        if "incident_relations" in json:
            # collect related incident ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["incident_relations"]:
                incident = Incident.query.get(relation["incident"]["id"])
                if incident:
                    rel_ids.append(incident.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_incident(incident, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination incident no in the related ids

            for r in self.incident_relations:
                # get related bulletin (in or out)
                if not (r.incident_id in rel_ids):
                    rel_incident = r.incident
                    r.delete()

                    # --revision relation
                    rel_incident.create_revision()

        # Related actors (actors_relations)
        if "actor_relations" in json:
            # collect related actor ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["actor_relations"]:
                actor = Actor.query.get(relation["actor"]["id"])
                if actor:
                    rel_ids.append(actor.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_actor(actor, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination actor no in the related ids

            for r in self.actor_relations:
                # get related bulletin (in or out)
                if not (r.actor_id in rel_ids):
                    rel_actor = r.actor
                    r.delete()

                    # --revision relation
                    rel_actor.create_revision()

        if "comments" in json:
            self.comments = json["comments"]

        if "status" in json:
            self.status = json["status"]

        return self

    # Compact dict for relationships
    @check_roles
    def to_compact(self):
        # locations json
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.to_dict())

        #aliases json
        aliases_json = []
        if self.aliases and len(self.aliases):
            for alias in self.aliases:
                aliases_json.append(alias.to_dict())

        #roles within json
        roles_within_json = []
        if self.roles_within and len(self.roles_within):
            for role in self.roles_within:
                roles_within_json.append(role.to_dict())

        # Social media handles json 
        handles_json = []
        if self.social_media_handles and len(self.social_media_handles):
            for handle in self.social_media_handles:
                handles_json.append(handle.to_dict_organization())

        # Events json
        events_json = []
        if self.events and len(self.events):
            for event in self.events:
                events_json.append(event.to_dict())

        return {
            "id": self.id,
            "name": self.name,
            "name_ar": self.name_ar,
            "locations": locations_json,
            "aliases": aliases_json,
            "events": events_json,
            "roles_within": roles_within_json,
            "social_media_handles": handles_json,
            "founded_date": DateHelper.serialize_datetime(self.founded_date),
            "description": self.description or None,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "comments": self.comments or "",
        }

    def to_csv_dict(self):

        output = {
            'id': self.id,
            'name': self.serialize_column('name'),
            'name_ar': self.serialize_column('name_ar'),
            'description': self.serialize_column('description'),
            'created_at': self.serialize_column('created_at'),
            'organization_type': self.serialize_column('organization_type'),
            'locations': convert_simple_relation(self.locations),
            'roles_within': convert_simple_relation(self.roles_within),
            'aliases': convert_simple_relation(self.aliases),
            'related_primary_records': convert_complex_relation(self.bulletin_relations_dict, Bulletin.__tablename__),
            'related_organizations': convert_complex_relation(self.organization_relations_dict, Organization.__tablename__),
            'related_investigations': convert_complex_relation(self.incident_relations_dict, Incident.__tablename__),
            'related_actors': convert_complex_relation(self.actor_relations_dict, Actor.__tablename__),
        }
        return output

    # Helper method to handle logic of relating organizations  (from organization)
    def relate_organization(self, organization, relation=None, create_revision=True):
        # if a new organization is being created, we must save it to get the id
        if not self.id:
            self.save()

        # Relationships are alwasy forced to go from the lower id to the bigger id (to prevent duplicates)
        # Enough to look up the relationship from the lower to the upper

        # reject self relation
        if self == organization:
            # Cant relate organization to itself
            return

        existing_relation = Otoo.are_related(self.id, organization.id)

        if existing_relation:
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation (possible from or to the organization based on the id comparison)
            new_relation = Otoo.relate(self, organization)

            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # ------- create revision on the other side of the relationship
            if create_revision:
                organization.create_revision()

    # Helper method to handle logic of relating incidents (from a organization)

    def relate_incident(self, incident, relation=None, create_revision=True):
        # if current organization is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (incident_id,organization_id)
        existing_relation = Otoi.query.get((incident.id, self.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Otoi(incident_id=incident.id, organization_id=self.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # --revision relation
            if create_revision:
                incident.create_revision()

    # helper method to relate bulletins
    def relate_bulletin(self, bulletin, relation=None, create_revision=True):
        # if current bulletin is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (organization_id,bulletin_id)
        existing_relation = Otob.query.get((self.id, bulletin.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Otob(organization_id=self.id, bulletin_id=bulletin.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # --revision relation
            if create_revision:
                bulletin.create_revision()

    # helper method to relate actors
    def relate_actor(self, actor, relation=None, create_revision=True):
        # if current actor is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (organization_id,actor_id)
        existing_relation = Otoa.query.get((self.id, actor.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Otoa(organization_id=self.id, actor_id=actor.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # --revision relation
            if create_revision:
                actor.create_revision()

    # custom serialization method
    @check_roles
    def to_dict(self, mode=None):
        if mode == '2':
            return self.to_mode2()
        if mode == '1':
            return self.min_json()

        # locations json
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.to_dict())

        handles_json = []
        if self.social_media_handles and len(self.social_media_handles):
            for handle in self.social_media_handles:
                handles_json.append(handle.to_dict_organization())

        # Events json
        events_json = []
        if self.events and len(self.events):
            for event in self.events:
                events_json.append(event.to_dict())

        # Related bulletins json (actually the associated relationships)
        # - in this case the other bulletin carries the relationship
        organization_relations_dict = []
        bulletin_relations_dict = []
        incident_relations_dict = []
        actor_relations_dict = []

        if str(mode) != '3':
            for relation in self.organization_relations:
                organization_relations_dict.append(relation.to_dict(exclude=self))

            # Related bulletin json (actually the associated relationships)
            for relation in self.bulletin_relations:
                bulletin_relations_dict.append(relation.to_dict())

            # Related incidents json (actually the associated relationships)
            for relation in self.incident_relations:
                incident_relations_dict.append(relation.to_dict())

            for relation in self.actor_relations:
                actor_relations_dict.append(relation.to_dict())

        return {
            "class": self.__tablename__,
            "id": self.id,
            "name": self.name,
            "name_ar": self.name_ar,
            "founded_date": DateHelper.serialize_datetime(self.founded_date),
            "aliases": [alias.to_dict() for alias in self.aliases] if self.aliases else [],
            # assigned to
            "assigned_to": self.assigned_to.to_compact() if self.assigned_to else None,
            "created_by": self.created_by.to_compact() if self.created_by else None,
            # first peer reviewer
            "first_peer_reviewer": self.first_peer_reviewer.to_compact()
            if self.first_peer_reviewer_id
            else None,
            "locations": locations_json,
            "roles_within": [role.to_dict() for role in self.roles_within] if self.roles_within else [],
            "organization_type": self.organization_type.to_dict() if self.organization_type else None,
            "social_media_handles": handles_json,
            "bulletin_relations": bulletin_relations_dict,
            "organization_relations": organization_relations_dict,
            "incident_relations": incident_relations_dict,
            "actor_relations": actor_relations_dict,
            "events": events_json,
            "description": self.description or None,
            "comments": self.comments or None,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "status": self.status,
            "review": self.review if self.review else None,
            "review_action": self.review_action if self.review_action else None,
            "updated_at": DateHelper.serialize_datetime(self.get_modified_date()),
            "roles": [role.to_dict() for role in self.roles] if self.roles else [],
        }

    # custom serialization mode
    def to_mode2(self):
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.to_dict())

        return {
            "class": "Organization",
            "id": self.id,
            "name": self.name,
            "name_ar": self.name_ar,
            # assigned to
            "locations": locations_json,
            "aliases": [alias.to_dict() for alias in self.aliases] if self.aliases else [],
            "roles_within": [role.to_dict() for role in self.roles_within] if self.roles_within else [],
            "description": self.description or None,
            "comments": self.comments or None,
            "created_at": DateHelper.serialize_datetime(self.created_at),

        }

    def to_json(self, export=False):
        organization_to_dict = self.to_dict()
        if export:
            organization_to_dict = export_json_rename_handler(organization_to_dict)
        return json.dumps(organization_to_dict)

    @staticmethod
    def get_columns():
        columns = []
        for column in Bulletin.__table__.columns:
            columns.append(column.name)
        return columns

    def get_modified_date(self):

        if self.history:
            return self.history[-1].updated_at
        else:
            return self.updated_at


class OtooInfo(db.Model, BaseMixin):
    """
    SQL Alchemy model for organization to organization relationship info
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


class Otoo(db.Model, BaseMixin):
    """
    Organization to organization relationship model
    """
    extend_existing = True

    # This constraint will make sure only one relationship exists across organizations (and prevent self relation)
    __table_args__ = (db.CheckConstraint("organization_id < related_organization_id"),)

    # Source organization
    # Available Backref: organization_from
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), primary_key=True)

    # Target organization
    # Available Backref: organization_to
    related_organization_id = db.Column(
        db.Integer, db.ForeignKey("organization.id"), primary_key=True
    )

    # Relationship extra fields
    related_as = db.Column(ARRAY(db.Integer))
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_otoos", foreign_keys=[user_id])

    @property
    def relation_info(self):
        related_infos = OtooInfo.query.filter(OtooInfo.id.in_(self.related_as)).all() if self.related_as else []
        # Return the to_dict representation of each of them
        return [info.to_dict() for info in related_infos]

    # Check if two organizations are related , if so return the relation, otherwise false
    @staticmethod
    def are_related(a_id, b_id):

        if a_id == b_id:
            return False

        # with our id constraint set, just check if there is relation from the lower id to the upper id
        f, t = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        relation = Otoo.query.get((f, t))
        if relation:
            return relation
        else:
            return False

    # Give an id, get the other organization id (relating in or out)
    def get_other_id(self, id):
        if id in (self.organization_id, self.related_organization_id):
            return (
                self.organization_id
                if id == self.related_organization_id
                else self.related_organization_id
            )
        return None

    # Create and return a relation between two organizations making sure the relation goes from the lower id to the upper id
    @staticmethod
    def relate(a, b):
        f, t = min(a.id, b.id), max(a.id, b.id)
        return Otoo(organization_id=f, related_organization_id=t)

    @staticmethod
    def relate_by_id(a, b):
        f, t = min(a, b), max(a, b)
        return Otoo(organization_id=f, related_organization_id=t)

    # Exclude the primary organization from output to get only the related/relating organization
    @check_relation_roles
    def to_dict(self, exclude=None):
        if not exclude:
            return {
                "organization_from": self.organization_from.to_compact(),
                "organization_to": self.organization_to.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }
        else:
            organization = self.organization_to if exclude == self.organization_from else self.organization_from

            return {
                "organization": organization.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }

    # this will update only relationship data
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class OtobInfo(db.Model, BaseMixin):
    """
    SQL Alchemy model for organization to bulletin relationship info
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


class Otob(db.Model, BaseMixin):
    """
    Organization to bulletin relationship model
    """
    extend_existing = True

    # Available Backref: bulletin
    bulletin_id = db.Column(db.Integer, db.ForeignKey("bulletin.id"), primary_key=True)

    # Available Backref: organization
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), primary_key=True)

    # Relationship extra fields
    # enabling multiple relationship types
    related_as = db.Column(ARRAY(db.Integer))
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_otobs", foreign_keys=[user_id])

    # Exclude the primary bulletin from output to get only the related/relating bulletin
    @property
    def relation_info(self):
        # Query the AtobInfo table based on the related_as list
        related_infos = OtobInfo.query.filter(OtobInfo.id.in_(self.related_as)).all() if self.related_as else []
        # Return the to_dict representation of each of them
        return [info.to_dict() for info in related_infos]

    # custom serialization method
    def to_dict(self):

        return {
            "bulletin": self.bulletin.to_compact(),
            "organization": self.organization.to_compact(),
            "related_as": self.related_as or [],
            "probability": self.probability,
            "comment": self.comment,
            "user_id": self.user_id,
        }

    # this will update only relationship data
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class OtoiInfo(db.Model, BaseMixin):
    """
    Otoi Relation Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


class Otoi(db.Model, BaseMixin):
    """
    Organization to investigation relationship model
    """
    extend_existing = True

    # Available Backref: organization
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), primary_key=True)

    # Available Backref: incident
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), primary_key=True)

    # Relationship extra fields
    related_as = db.Column(ARRAY(db.Integer))
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_otois", foreign_keys=[user_id])

    @property
    def relation_info(self):
        # Query the AtobInfo table based on the related_as list
        related_infos = OtoiInfo.query.filter(OtoiInfo.id.in_(self.related_as)).all() if self.related_as else []
        # Return the to_dict representation of each of them
        return [info.to_dict() for info in related_infos]

    # custom serialization method
    def to_dict(self):

        return {
            "organization": self.organization.to_compact(),
            "incident": self.incident.to_compact(),
            "related_as": self.related_as,
            "probability": self.probability,
            "comment": self.comment,
            "user_id": self.user_id,
        }

    # this will update only relationship data, (populates it from json dict)
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self

class OtoaInfo(db.Model, BaseMixin):
    """
    Otoa Relation Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


class Otoa(db.Model, BaseMixin):
    """
    Organization to actor relationship model
    """
    extend_existing = True

    # Available Backref: organization
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), primary_key=True)

    # Available Backref: actor
    actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"), primary_key=True)

    # Relationship extra fields
    related_as = db.Column(ARRAY(db.Integer))
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_otoas", foreign_keys=[user_id])

    @property
    def relation_info(self):
        # Query the AtobInfo table based on the related_as list
        related_infos = OtoaInfo.query.filter(OtoaInfo.id.in_(self.related_as)).all() if self.related_as else []
        # Return the to_dict representation of each of them
        return [info.to_dict() for info in related_infos]

    # custom serialization method
    def to_dict(self):

        return {
            "organization": self.organization.to_compact(),
            "actor": self.actor.to_compact(),
            "related_as": self.related_as,
            "probability": self.probability,
            "comment": self.comment,
            "user_id": self.user_id,
        }

    # this will update only relationship data, (populates it from json dict)
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class Actor(db.Model, BaseMixin):
    """
    SQL Alchemy model for actors
    """

    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255))
    name_ar = db.Column(db.String(255))

    description = db.Column(db.Text)

    credibility = db.Column(db.Integer)
    
    aliases = db.relationship('Alias', back_populates='actor', cascade='all, delete-orphan')

    first_name = db.Column(db.String(255))
    first_name_ar = db.Column(db.String(255))

    middle_name = db.Column(db.String(255))
    middle_name_ar = db.Column(db.String(255))

    last_name = db.Column(db.String(255))
    last_name_ar = db.Column(db.String(255))

    mother_name = db.Column(db.String(255))
    mother_name_ar = db.Column(db.String(255))

    originid = db.Column(db.String(255))

    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    assigned_to = db.relationship(
        "User", backref="assigned_to_actors", foreign_keys=[assigned_to_id]
    )

    first_peer_reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    second_peer_reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    first_peer_reviewer = db.relationship(
        "User", backref="first_rev_actors", foreign_keys=[first_peer_reviewer_id]
    )
    second_peer_reviewer = db.relationship(
        "User", backref="second_rev_actors", foreign_keys=[second_peer_reviewer_id]
    )

    social_media_handles = db.relationship('SocialMediaHandle', back_populates='actor')
    
    sanction_regimes = db.relationship('SanctionRegimeToActor', back_populates='actor')

    sub_type_id = db.Column(db.Integer, db.ForeignKey(ActorSubType.id))
    sub_type = db.relationship("ActorSubType", back_populates="actors", foreign_keys=[sub_type_id])

    sources = db.relationship(
        "Source", secondary=actor_sources, backref=db.backref("actors", lazy="dynamic")
    )

    labels = db.relationship(
        "Label", secondary=actor_labels, backref=db.backref("actors", lazy="dynamic")
    )

    ver_labels = db.relationship(
        "Label", secondary=actor_verlabels, backref=db.backref("verlabels_actors", lazy="dynamic"),
    )

    roles = db.relationship(
        "Role",
        secondary=actor_roles,
        backref=db.backref("actors", lazy="dynamic")
    )

    events = db.relationship(
        "Event",
        secondary=actor_events,
        backref=db.backref("actors", lazy="dynamic"),
        order_by="Event.from_date"
    )

    # Actors that this actor relate to ->
    actors_to = db.relationship(
        "Atoa", backref="actor_from", foreign_keys="Atoa.actor_id"
    )

    # Actors that relate to this <-
    actors_from = db.relationship(
        "Atoa", backref="actor_to", foreign_keys="Atoa.related_actor_id"
    )

    # Related Bulletins
    related_bulletins = db.relationship(
        "Atob", backref="actor", foreign_keys="Atob.actor_id"
    )

    # Related Incidents
    related_incidents = db.relationship(
        "Itoa", backref="actor", foreign_keys="Itoa.actor_id"
    )

    related_organizations = db.relationship(
        "Otoa", backref="actor", foreign_keys="Otoa.actor_id"
    )

    actor_type = db.Column(db.String(255))
    sex = db.Column(Enum(Sex))
    age = db.Column(db.String(255))
    civilian = db.Column(db.String(255))
    birth_date = db.Column(db.DateTime)

    birth_place_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    birth_place = db.relationship(
        "Location", backref="actors_born", foreign_keys=[birth_place_id]
    )

    residence_place_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    residence_place = db.relationship(
        "Location", backref="actors_residence_place", foreign_keys=[residence_place_id]
    )
    origin_place_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    origin_place = db.relationship(
        "Location", backref="actors_origin_place", foreign_keys=[origin_place_id]
    )

    organization_roles = db.relationship('OrganizationRoleActor', back_populates='actor', foreign_keys='OrganizationRoleActor.actor_id')

    occupation = db.Column(db.String(255))
    occupation_ar = db.Column(db.String(255))

    position = db.Column(db.String(255))
    position_ar = db.Column(db.String(255))

    dialects = db.Column(db.String(255))
    dialects_ar = db.Column(db.String(255))

    family_status = db.Column(db.String(255))
    family_status_ar = db.Column(db.String(255))

    ethnographies = db.relationship('Ethnography', secondary='actor_ethnographies',
                                    backref=db.backref('actors', lazy='dynamic'))

    nationalities = db.relationship('Country',
                                    secondary=actor_countries,
                                    backref=db.backref('actors', lazy='dynamic'))

    national_id_card = db.Column(db.String(255))

    publish_date = db.Column(db.DateTime, index=True)
    documentation_date = db.Column(db.DateTime, index=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_by = db.relationship(
        "User", backref="create_by_actors", foreign_keys=[created_by_id]
    )

    status = db.Column(db.String(255))
    source_link = db.Column(db.String(255))
    sensitive_data = db.Column(db.Boolean, default=False)
    comments = db.Column(db.Text)
    # review fields
    review = db.Column(db.Text)
    review_action = db.Column(db.String)

    # metadata
    meta = db.Column(JSONB)

    tsv = db.Column(TSVECTOR)

    if cfg.MISSING_PERSONS:
        last_address = db.Column(db.Text)
        social_networks = db.Column(JSONB)
        marriage_history = db.Column(db.String)
        bio_children = db.Column(db.Integer)
        pregnant_at_disappearance = db.Column(db.String)
        months_pregnant = db.Column(db.Integer)
        missing_relatives = db.Column(db.Boolean)
        saw_name = db.Column(db.String)
        saw_address = db.Column(db.Text)
        saw_email = db.Column(db.String)
        saw_phone = db.Column(db.String)
        detained_before = db.Column(db.String)
        seen_in_detention = db.Column(JSONB)
        injured = db.Column(JSONB)
        known_dead = db.Column(JSONB)
        death_details = db.Column(db.Text)
        personal_items = db.Column(db.Text)
        height = db.Column(db.Integer)
        weight = db.Column(db.Integer)
        physique = db.Column(db.String)
        hair_loss = db.Column(db.String)
        hair_type = db.Column(db.String)
        hair_length = db.Column(db.String)
        hair_color = db.Column(db.String)
        facial_hair = db.Column(db.String)
        posture = db.Column(db.Text)
        skin_markings = db.Column(JSONB)
        handedness = db.Column(db.String)
        glasses = db.Column(db.String)
        eye_color = db.Column(db.String)
        dist_char_con = db.Column(db.String)
        dist_char_acq = db.Column(db.String)
        physical_habits = db.Column(db.String)
        other = db.Column(db.Text)
        phys_name_contact = db.Column(db.Text)
        injuries = db.Column(db.Text)
        implants = db.Column(db.Text)
        malforms = db.Column(db.Text)
        pain = db.Column(db.Text)
        other_conditions = db.Column(db.Text)
        accidents = db.Column(db.Text)
        pres_drugs = db.Column(db.Text)
        smoker = db.Column(db.String)
        dental_record = db.Column(db.Boolean)
        dentist_info = db.Column(db.Text)
        teeth_features = db.Column(db.Text)
        dental_problems = db.Column(db.Text)
        dental_treatments = db.Column(db.Text)
        dental_habits = db.Column(db.Text)
        case_status = db.Column(db.String)
        # array of objects: name, email,phone, email, address, relationship
        reporters = db.Column(JSONB)
        identified_by = db.Column(db.String)
        family_notified = db.Column(db.Boolean)
        hypothesis_based = db.Column(db.Text)
        hypothesis_status = db.Column(db.String)

        # death_cause = db.Column(db.String)
        reburial_location = db.Column(db.String)

    search = db.Column(db.Text, db.Computed("""
         (id)::text || ' ' ||
         COALESCE(name, ''::character varying) || ' ' ||
         COALESCE(name_ar, ''::character varying) || ' ' ||
         COALESCE(originid, ''::character varying) || ' ' ||
         COALESCE(source_link, ''::character varying) || ' ' ||
         COALESCE(description, ''::text) || ' ' ||
         COALESCE(comments, ''::text)
        """))

    __table_args__ = (
        db.Index('ix_actor_search', 'search', postgresql_using="gin", postgresql_ops={'search': 'gin_trgm_ops'}),
        db.CheckConstraint("name IS NOT NULL OR name_ar IS NOT NULL", name="check_name"),
    )

    # helper method to create a revision
    def create_revision(self, user_id=None, created=None):
        if not user_id:
            user_id = getattr(current_user, 'id', 1)

        a = ActorHistory(
            actor_id=self.id, data=self.to_dict(), user_id=user_id
        )
        if created:
            a.created_at = created
            a.updated_at = created
        a.save()
        print("created actor revision ")

    # returns all related actors
    @property
    def actor_relations(self):
        return self.actors_to + self.actors_from

    # returns all related bulletins
    @property
    def bulletin_relations(self):
        return self.related_bulletins

    # returns all related incidents
    @property
    def incident_relations(self):
        return self.related_incidents

    # returns all related organizations
    @property
    def organization_relations(self):
        return self.related_organizations

    @property
    def actor_relations_dict(self):
        return [relation.to_dict(exclude=self) for relation in self.actor_relations]

    @property
    def bulletin_relations_dict(self):
        return [relation.to_dict() for relation in self.bulletin_relations]

    @property
    def incident_relations_dict(self):
        return [relation.to_dict() for relation in self.incident_relations]

    @property
    def organization_relations_dict(self):
        return [relation.to_dict() for relation in self.organization_relations]

    # populate actor object from json dict
    def from_json(self, json):
        # All text fields
        # assigned to
        if "assigned_to" in json and json["assigned_to"] and "id" in json["assigned_to"]:
            self.assigned_to_id = json["assigned_to"]["id"]

        # created by
        if "created_by" in json and json["created_by"] and "id" in json["created_by"]:
            self.created_by_id = json["created_by"]["id"]

        self.originid = json["originid"] if "originid" in json else None
        self.name = json["name"] if "name" in json else None
        self.name_ar = json["name_ar"] if "name_ar" in json else None

        self.first_name = json["first_name"] if "first_name" in json else None
        self.first_name_ar = json["first_name_ar"] if "first_name_ar" in json else None

        self.middle_name = json["middle_name"] if "middle_name" in json else None
        self.middle_name_ar = (
            json["middle_name_ar"] if "middle_name_ar" in json else None
        )

        self.last_name = json["last_name"] if "last_name" in json else None
        self.last_name_ar = json["last_name_ar"] if "last_name_ar" in json else None

        self.mother_name = json["mother_name"] if "mother_name" in json else None
        self.mother_name_ar = (
            json["mother_name_ar"] if "mother_name_ar" in json else None
        )

        self.description = json["description"] if "description" in json else None
        self.credibility = json["credibility"] if "credibility" in json else None

        self.occupation = json["occupation"] if "occupation" in json else None
        self.occupation_ar = json["occupation_ar"] if "occupation_ar" in json else None
        self.position = json["position"] if "position" in json else None
        self.position_ar = json["position_ar"] if "position_ar" in json else None
        self.dialects = json["dialects"] if "dialects" in json else None
        self.dialects_ar = json["dialects_ar"] if "dialects_ar" in json else None
        self.family_status = json["family_status"] if "family_status" in json else None
        self.family_status_ar = (
            json["family_status_ar"] if "family_status_ar" in json else None
        )


        self.national_id_card = (
            json["national_id_card"] if "national_id_card" in json else None
        )

        self.source_link = json["source_link"] if "source_link" in json else None
        self.sensitive_data = json.get('sensitive_data')

        if "sub_type" in json and json["sub_type"] and "id" in json["sub_type"]:
            self.sub_type_id = json["sub_type"]["id"]

        # Ethnographies
        if "ethnography" in json:
            ids = [ethnography.get('id') for ethnography in json["ethnography"]]
            ethnographies = Ethnography.query.filter(Ethnography.id.in_(ids)).all()
            self.ethnographies = ethnographies

        # Nationalitites
        if "nationality" in json:
            ids = [country.get('id') for country in json["nationality"]]
            countries = Country.query.filter(Country.id.in_(ids)).all()
            self.nationalities = countries


        # Sources
        if "sources" in json:
            ids = [source["id"] for source in json["sources"]]
            sources = Source.query.filter(Source.id.in_(ids)).all()
            self.sources = sources

        # Labels
        if "labels" in json:
            ids = [label["id"] for label in json["labels"]]
            labels = Label.query.filter(Label.id.in_(ids)).all()
            self.labels = labels

        # verified Labels
        if "verLabels" in json:
            ids = [label["id"] for label in json["verLabels"]]
            ver_labels = Label.query.filter(Label.id.in_(ids)).all()
            self.ver_labels = ver_labels

        if "sex" in json and json["sex"]:
            if Sex.is_valid(json["sex"]):
                self.sex = Sex.get_name(json["sex"])
            else:
                raise ValueError(f"{json['sex']} is not a valid option for an actor's sex")

        self.age = json["age"] if "age" in json else None
        self.civilian = json["civilian"] if "civilian" in json else None
        self.actor_type = json["actor_type"] if "actor_type" in json else None

        if "birth_date" in json and json["birth_date"]:
            self.birth_date = json["birth_date"]
        else:
            self.birth_date = None

        if "birth_place" in json and json["birth_place"] and "id" in json["birth_place"]:
            self.birth_place_id = json["birth_place"]["id"]
        else:
            self.birth_place_id = None

        if "residence_place" in json and json["residence_place"] and "id" in json["residence_place"]:
            self.residence_place_id = json["residence_place"]["id"]
        else:
            self.residence_place_id = None

        if "origin_place" in json and json["origin_place"] and "id" in json["origin_place"]:
            self.origin_place_id = json["origin_place"]["id"]
        else:
            self.origin_place_id = None

        # Events
        if "events" in json:
            new_events = []
            events = json["events"]

            for event in events:
                g = None
                #if event["geo_location"]:
                if "geo_location" in event and "custom_location" in event and event["custom_location"] is True:
                    geo_location = event["geo_location"]
                    
                    if "id" not in geo_location:
                        # new geolocation
                        g = GeoLocation()
                        g.from_json(geo_location)
                        g.save()
                    else:
                        # geolocation exists // update
                        g = GeoLocation.query.get(geo_location['id'])
                        g.from_json(geo_location)
                        g.save()
                
                    if "id" not in event:
                        # new event
                        e = Event()
                        e = e.from_json(event)
                        if g is not None:
                            e.geo_location = g
                        e.save()
                        new_events.append(e)
                    else:
                        # event already exists, get a db instnace and update it with new data
                        e = Event.query.get(event["id"])
                        e.from_json(event)
                        if g is not None:
                            e.geo_location = g
                        e.save()
                        new_events.append(e)
                else:
                    if "id" not in event:
                        # new event
                        e = Event()
                        e = e.from_json(event)
                        e.save()
                    else:
                        # event already exists, get a db instnace and update it with new data
                        e = Event.query.get(event["id"])
                        e.from_json(event)
                        e.save()
                    new_events.append(e)
                            
            self.events = new_events

        if "aliases" in json:
            new_aliases = []
            aliases = json["aliases"]
            for alias in aliases:
                if "id" not in alias:
                    # new alias
                    a = Alias()
                    a = a.from_json(alias)
                    a.save()
                else:
                    # alias already exists, get a db instance and update it with new data
                    a = Alias.query.get(alias["id"])
                    a.from_json(alias)
                    a.save()
                new_aliases.append(a)
            self.aliases = new_aliases

        # Social Media Handles
        if "social_media_handles" in json:
            new_handles = []
            handles = json["social_media_handles"]
            for handle in handles:
                if "id" not in handle:
                    # new handle
                    h = SocialMediaHandle()
                    h = h.from_json(handle)
                    h.save()
                else:
                    # handle already exists, get a db instance and update it with new data
                    h = SocialMediaHandle.query.get(handle["id"])
                    h.from_json(handle)
                    h.save()
                new_handles.append(h)
            self.social_media_handles = new_handles

        if "sanction_regimes" in json:
            new_sanction_regime_to_actors = []
            sanction_regimes = json["sanction_regimes"]
            for regime in sanction_regimes:
                if "id" not in regime:
                    # new sanction_regime_to_actor
                    sr_to_a = SanctionRegimeToActor()
                    sr_to_a = sr_to_a.from_json(regime)
                    sr_to_a.save()
                else:
                    # sanction_regime_to_actor already exists, get a db instance and update it with new data
                    sr_to_a = SanctionRegimeToActor.query.get(regime["id"])
                    sr_to_a.from_json(regime)
                    sr_to_a.save()
                new_sanction_regime_to_actors.append(sr_to_a)
            self.sanction_regimes = new_sanction_regime_to_actors

        if "roles" in json:
            ids = [role["id"] for role in json["roles"]]
            roles = Role.query.filter(Role.id.in_(ids)).all()
            self.roles = roles

        # Related Media
        if "medias" in json:
            # untouchable main medias
            main = [m for m in self.medias if m.main is True]
            others = [m for m in self.medias if not m.main]
            to_keep_ids = [m.get('id') for m in json.get('medias') if m.get('id')]

            # handle removed medias
            to_be_deleted = [m for m in others if m.id not in to_keep_ids]

            others = [m for m in others if m.id in to_keep_ids]
            to_be_created = [m for m in json.get('medias') if not m.get('id')]

            new_medias = []
            # create new medias
            for media in to_be_created:
                m = Media()
                m = m.from_json(media)
                m.save()
                new_medias.append(m)

            self.medias = main + others + new_medias

            # mark removed media as deleted
            for media in to_be_deleted:
                media.deleted = True
                delete_comment = f'Removed from Actor #{self.id}'
                media.comments = media.comments + '\n' + delete_comment if media.comments else delete_comment
                media.save()

        self.publish_date = json.get('publish_date', None)
        if self.publish_date == '':
            self.publish_date = None
        self.documentation_date = json.get('documentation_date', None)
        if self.documentation_date == '':
            self.documentation_date = None

        # Related Actors (actor_relations)
        if "actor_relations" in json:
            # collect related actors ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["actor_relations"]:
                actor = Actor.query.get(relation["actor"]["id"])

                # Extra (check those actors exit)

                if actor:
                    rel_ids.append(actor.id)
                    # this will update/create the relationship (will flush to db!)
                    self.relate_actor(actor, relation=relation)

                # Find out removed relations and remove them
            # just loop existing relations and remove if the destination actor not in the related ids

            for r in self.actor_relations:
                # get related actor (in or out)
                rid = r.get_other_id(self.id)
                if not (rid in rel_ids):
                    r.delete()

                    # -revision related
                    Actor.query.get(rid).create_revision()

        # Related Bulletins (bulletin_relations)
        if "bulletin_relations" in json:
            # collect related bulletin ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["bulletin_relations"]:
                bulletin = Bulletin.query.get(relation["bulletin"]["id"])

                # Extra (check those bulletins exit)
                if bulletin:
                    rel_ids.append(bulletin.id)
                    # this will update/create the relationship (will flush to db!)
                    self.relate_bulletin(bulletin, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination bulletin not in the related ids
            for r in self.bulletin_relations:
                if not (r.bulletin_id in rel_ids):
                    rel_bulletin = r.bulletin
                    r.delete()

                    # -revision related
                    rel_bulletin.create_revision()

        # Related Incidents (incidents_relations)
        if "incident_relations" in json:
            # collect related incident ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["incident_relations"]:
                incident = Incident.query.get(relation["incident"]["id"])
                if incident:
                    rel_ids.append(incident.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_incident(incident, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination incident no in the related ids

            for r in self.incident_relations:
                # get related bulletin (in or out)
                if not (r.incident_id in rel_ids):
                    rel_incident = r.incident
                    r.delete()

                    # -revision related incident
                    rel_incident.create_revision()

        # Related Organizations (organizations_relations)
        if "organization_relations" in json:
            # collect related organization ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["organization_relations"]:
                organization = Organization.query.get(relation["organization"]["id"])
                if organization:
                    rel_ids.append(organization.id)
                    # helper method to update/create the relationship (will flush to db)
                    self.relate_organization(organization, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination organization is not in the related ids

            for r in self.organization_relations:
                # get related bulletin (in or out)
                if not (r.organization_id in rel_ids):
                    rel_organization = r.organization
                    r.delete()

                    # -revision related organization
                    rel_organization.create_revision()

        if "comments" in json:
            self.comments = json["comments"]

        if "status" in json:
            self.status = json["status"]

        # Missing Persons
        if cfg.MISSING_PERSONS:
            self.last_address = json.get('last_address')
            self.marriage_history = json.get('marriage_history')
            self.bio_children = json.get('bio_children')
            self.pregnant_at_disappearance = json.get('pregnant_at_disappearance')
            self.months_pregnant = json.get('months_pregnant')
            self.missing_relatives = json.get('missing_relatives')
            self.saw_name = json.get('saw_name')
            self.saw_address = json.get('saw_address')
            self.saw_phone = json.get('saw_phone')
            self.saw_email = json.get('saw_email')
            self.seen_in_detention = json.get('seen_in_detention')
            # Flag json fields for saving
            flag_modified(self, 'seen_in_detention')
            self.injured = json.get('injured')
            flag_modified(self, 'injured')
            self.known_dead = json.get('known_dead')
            flag_modified(self, 'known_dead')
            self.death_details = json.get('death_details')
            self.personal_items = json.get('personal_items')
            self.height = json.get('height')
            self.weight = json.get('weight')
            self.physique = json.get('physique')
            self.hair_loss = json.get('hair_loss')
            self.hair_type = json.get('hair_type')
            self.hair_length = json.get('hair_length')
            self.hair_color = json.get('hair_color')
            self.facial_hair = json.get('facial_hair')
            self.posture = json.get('posture')
            self.skin_markings = json.get('skin_markings')
            flag_modified(self, 'skin_markings')
            self.handedness = json.get('handedness')
            self.eye_color = json.get('eye_color')
            self.glasses = json.get('glasses')
            self.dist_char_con = json.get('dist_char_con')
            self.dist_char_acq = json.get('dist_char_acq')
            self.physical_habits = json.get('physical_habits')
            self.other = json.get('other')
            self.phys_name_contact = json.get('phys_name_contact')
            self.injuries = json.get('injuries')
            self.implants = json.get('implants')
            self.malforms = json.get('malforms')
            self.pain = json.get('pain')
            self.other_conditions = json.get('other_conditions')
            self.accidents = json.get('accidents')
            self.pres_drugs = json.get('pres_drugs')
            self.smoker = json.get('smoker')
            self.dental_record = json.get('dental_record')
            self.dentist_info = json.get('dentist_info')
            self.teeth_features = json.get('teeth_features')
            self.dental_problems = json.get('dental_problems')
            self.dental_treatments = json.get('dental_treatments')
            self.dental_habits = json.get('dental_habits')
            self.case_status = json.get('case_status')
            self.reporters = json.get('reporters')
            flag_modified(self, 'reporters')
            self.identified_by = json.get('identified_by')
            self.family_notified = json.get('family_notified')
            self.reburial_location = json.get('reburial_location')
            self.hypothesis_based = json.get('hypothesis_based')
            self.hypothesis_status = json.get('hypothesis_status')

        return self

    def mp_json(self):
        mp = {}
        mp['MP'] = True
        mp['last_address'] = getattr(self, 'last_address')
        mp['marriage_history'] = getattr(self, 'marriage_history')
        mp['bio_children'] = getattr(self, 'bio_children')
        mp['pregnant_at_disappearance'] = getattr(self, 'pregnant_at_disappearance')
        mp['months_pregnant'] = str(self.months_pregnant) if self.months_pregnant else None
        mp['missing_relatives'] = getattr(self, 'missing_relatives')
        mp['saw_name'] = getattr(self, 'saw_name')
        mp['saw_address'] = getattr(self, 'saw_address')
        mp['saw_phone'] = getattr(self, 'saw_phone')
        mp['saw_email'] = getattr(self, 'saw_email')
        mp['seen_in_detention'] = getattr(self, 'seen_in_detention')
        mp['injured'] = getattr(self, 'injured')
        mp['known_dead'] = getattr(self, 'known_dead')
        mp['death_details'] = getattr(self, 'death_details')
        mp['personal_items'] = getattr(self, 'personal_items')
        mp['height'] = str(self.height) if self.height else None
        mp['weight'] = str(self.weight) if self.weight else None
        mp['physique'] = getattr(self, 'physique')
        mp['_physique'] = getattr(self, 'physique')

        mp['hair_loss'] = getattr(self, 'hair_loss')
        mp['_hair_loss'] = gettext(self.hair_loss)

        mp['hair_type'] = getattr(self, 'hair_type')
        mp['_hair_type'] = gettext(self.hair_type)

        mp['hair_length'] = getattr(self, 'hair_length')
        mp['_hair_length'] = gettext(self.hair_length)

        mp['hair_color'] = getattr(self, 'hair_color')
        mp['_hair_color'] = gettext(self.hair_color)

        mp['facial_hair'] = getattr(self, 'facial_hair')
        mp['_facial_hair'] = gettext(self.facial_hair)

        mp['posture'] = getattr(self, 'posture')
        mp['skin_markings'] = getattr(self, 'skin_markings')
        if self.skin_markings and self.skin_markings.get('opts'):
            mp['_skin_markings'] = [gettext(item) for item in self.skin_markings['opts']]

        mp['handedness'] = getattr(self, 'handedness')
        mp['_handedness'] = gettext(self.handedness)
        mp['eye_color'] = getattr(self, 'eye_color')
        mp['_eye_color'] = gettext(self.eye_color)

        mp['glasses'] = getattr(self, 'glasses')
        mp['dist_char_con'] = getattr(self, 'dist_char_con')
        mp['dist_char_acq'] = getattr(self, 'dist_char_acq')
        mp['physical_habits'] = getattr(self, 'physical_habits')
        mp['other'] = getattr(self, 'other')
        mp['phys_name_contact'] = getattr(self, 'phys_name_contact')
        mp['injuries'] = getattr(self, 'injuries')
        mp['implants'] = getattr(self, 'implants')
        mp['malforms'] = getattr(self, 'malforms')
        mp['pain'] = getattr(self, 'pain')
        mp['other_conditions'] = getattr(self, 'other_conditions')
        mp['accidents'] = getattr(self, 'accidents')
        mp['pres_drugs'] = getattr(self, 'pres_drugs')
        mp['smoker'] = getattr(self, 'smoker')
        mp['dental_record'] = getattr(self, 'dental_record')
        mp['dentist_info'] = getattr(self, 'dentist_info')
        mp['teeth_features'] = getattr(self, 'teeth_features')
        mp['dental_problems'] = getattr(self, 'dental_problems')
        mp['dental_treatments'] = getattr(self, 'dental_treatments')
        mp['dental_habits'] = getattr(self, 'dental_habits')
        mp['case_status'] = getattr(self, 'case_status')
        mp['_case_status'] = gettext(self.case_status)
        mp['reporters'] = getattr(self, 'reporters')
        mp['identified_by'] = getattr(self, 'identified_by')
        mp['family_notified'] = getattr(self, 'family_notified')
        mp['reburial_location'] = getattr(self, 'reburial_location')
        mp['hypothesis_based'] = getattr(self, 'hypothesis_based')
        mp['hypothesis_status'] = getattr(self, 'hypothesis_status')
        return mp

    # Compact dict for relationships
    @check_roles
    def to_compact(self):
        # sources json
        sources_json = []
        if self.sources and len(self.sources):
            for source in self.sources:
                sources_json.append({"id": source.id, "title": source.title})

        return {
            "id": self.id,
            "name": self.name,
            "originid": self.originid or None,
            "sources": sources_json,
            "description": self.description or None,
            "source_link": self.source_link or None,
            "sensitive_data": getattr(self, "sensitive_data"),
            "publish_date": DateHelper.serialize_datetime(self.publish_date),
            "documentation_date": DateHelper.serialize_datetime(self.documentation_date),
        }

    def to_csv_dict(self):

        output = {
            'id': self.id,
            'name': self.serialize_column('name'),
            'name_ar': self.serialize_column('name_ar'),
            'middle_name': self.serialize_column('middle_name'),
            'middle_name_ar': self.serialize_column('middle_name_ar'),
            'last_name': self.serialize_column('last_name'),
            'last_name_ar': self.serialize_column('last_name_ar'),

            'mother_name': self.serialize_column('mother_name'),
            'mother_name_ar': self.serialize_column('mother_name_ar'),

            'sex': self.serialize_column('sex'),
            'age': self.serialize_column('age'),
            'civilian': self.serialize_column('civilian'),
            'actor_type': self.serialize_column('actor_type'),
            'birth_date': self.serialize_column('birth_date'),
            'birth_place': self.serialize_column('birth_place'),

            'description': self.serialize_column('description'),
            
            'credibility': self.serialize_column('credibility'),

            'publish_date': self.serialize_column('publish_date'),
            'documentation_date': self.serialize_column('documentation_date'),
            'sub_type': self.serialize_column('sub_type'),

            'aliases': convert_simple_relation(self.aliases),
            'labels': convert_simple_relation(self.labels),
            'verified_labels': convert_simple_relation(self.ver_labels),
            'sources': convert_simple_relation(self.sources),
            'media': convert_simple_relation(self.medias),
            'events': convert_simple_relation(self.events),
            'related_primary_records': convert_complex_relation(self.bulletin_relations_dict, Bulletin.__tablename__),
            'related_actors': convert_complex_relation(self.actor_relations_dict, Actor.__tablename__),
            'related_investigations': convert_complex_relation(self.incident_relations_dict, Incident.__tablename__),
            'related_organizations': convert_complex_relation(self.organization_relations_dict, Organization.__tablename__),

        }
        return output

    def get_modified_date(self):
        if self.history:
            return self.history[-1].updated_at
        else:
            return self.updated_at

    # Helper method to handle logic of relating actors (from actor)

    def relate_actor(self, actor, relation=None, create_revision=True):

        # if a new actor is being created, we must save it to get the id
        if not self.id:
            self.save()

        # Relationships are alwasy forced to go from the lower id to the bigger id (to prevent duplicates)
        # Enough to look up the relationship from the lower to the upper

        # reject self relation
        if self == actor:
            # Cant relate bulletin to itself
            return

        existing_relation = Atoa.are_related(self.id, actor.id)
        if existing_relation:
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation (possible from or to the actor based on the id comparison)
            new_relation = Atoa.relate(self, actor)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # revision for related actor
            if create_revision:
                actor.create_revision()

    # Helper method to handle logic of relating bulletin (from am actor)
    def relate_bulletin(self, bulletin, relation=None, create_revision=True):
        # if current actor is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (bulletin_id,actor_id)
        existing_relation = Atob.query.get((bulletin.id, self.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Atob(bulletin_id=bulletin.id, actor_id=self.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # revision for related bulletin
            if create_revision:
                bulletin.create_revision()

    # Helper method to handle logic of relating incidents (from an actor)
    def relate_incident(self, incident, relation=None, create_revision=True):
        # if current bulletin is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (actor_id,incident_id)
        existing_relation = Itoa.query.get((self.id, incident.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Itoa(actor_id=self.id, incident_id=incident.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # revision for related incident
            if create_revision:
                incident.create_revision()

    # Helper method to handle logic of relating organizations (from an actor)
    def relate_organization(self, organization, relation=None, create_revision=True):
        # if current bulletin is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (actor_id,organization_id)
        existing_relation = Otoa.query.get((self.id, organization.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Otoa(actor_id=self.id, organization_id=organization.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # revision for related organization
            if create_revision:
                organization.create_revision()

    @check_roles
    def to_dict(self, mode=None):

        if mode == '1':
            return self.min_json()
        if mode == '2':
            return self.to_mode2()

        # Sources json
        sources_json = []
        if self.sources and len(self.sources):
            for source in self.sources:
                sources_json.append({"id": source.id, "title": source.title})

        # Labels json
        labels_json = []
        if self.labels and len(self.labels):
            for label in self.labels:
                labels_json.append({"id": label.id, "title": label.title})

        # verified labels json
        ver_labels_json = []
        if self.ver_labels and len(self.ver_labels):
            for vlabel in self.ver_labels:
                ver_labels_json.append({"id": vlabel.id, "title": vlabel.title})

        # Events json
        events_json = []
        if self.events and len(self.events):
            for event in self.events:
                events_json.append(event.to_dict())

        # Social media handles json 
        handles_json = []
        if self.social_media_handles and len(self.social_media_handles):
            for handle in self.social_media_handles:
                handles_json.append(handle.to_dict_actor())
        
        # Sanction Regime json 
        regimes_json = []
        if self.sanction_regimes and len(self.sanction_regimes):
            for regime in self.sanction_regimes:
                regimes_json.append(regime.to_dict_actor())

        # medias json
        medias_json = []
        if self.medias and len(self.medias):

            for media in self.medias:
                medias_json.append(media.to_dict())

        aliases_json = []
        if self.aliases and len(self.aliases):
            for alias in self.aliases:
                aliases_json.append(alias.to_dict())

        bulletin_relations_dict = []
        actor_relations_dict = []
        incident_relations_dict = []
        organization_relations_dict = []

        if str(mode) != '3':
            # lazy load if mode is 3
            for relation in self.bulletin_relations:
                bulletin_relations_dict.append(relation.to_dict())

            for relation in self.actor_relations:
                actor_relations_dict.append(relation.to_dict(exclude=self))

            for relation in self.incident_relations:
                incident_relations_dict.append(relation.to_dict())

            for relation in self.organization_relations:
                organization_relations_dict.append(relation.to_dict())

        actor = {
            "class": self.__tablename__,
            "id": self.id,
            "originid": self.originid or None,
            "name": self.name or None,
            "name_ar": getattr(self, 'name_ar'),
            "description": self.description or None,
            "credibility": self.credibility or None,
            "_credibility": getCredibility(self.credibility) if self.credibility else None,
            "first_name": self.first_name or None,
            "first_name_ar": self.first_name_ar or None,
            "middle_name": self.middle_name or None,
            "middle_name_ar": self.middle_name_ar or None,
            "last_name": self.last_name or None,
            "last_name_ar": self.last_name_ar or None,
            "mother_name": self.mother_name or None,
            "mother_name_ar": self.mother_name_ar or None,
            "sex": self.sex.__str__() if self.sex else None,
            "_sex": gettext(self.sex.__str__()) if self.sex else None,
            "age": self.age,
            "_age": gettext(self.age),
            "civilian": self.civilian or None,
            "_civilian": gettext(self.civilian),
            "actor_type": self.actor_type,
            "_actor_type": gettext(self.actor_type),
            "occupation": self.occupation or None,
            "occupation_ar": self.occupation_ar or None,
            "position": self.position or None,
            "position_ar": self.position_ar or None,
            "dialects": self.dialects or None,
            "dialects_ar": self.dialects_ar or None,
            "family_status": self.family_status or None,
            "family_status_ar": self.family_status_ar or None,

            "ethnography": [ethnography.to_dict() for ethnography in getattr(self, 'ethnographies', [])],
            "nationality": [country.to_dict() for country in getattr(self, 'nationalities', [])],
            "national_id_card": self.national_id_card or None,
            # assigned to
            "assigned_to": self.assigned_to.to_compact() if self.assigned_to else None,
            "created_by": self.created_by.to_compact() if self.created_by else None,
            # first peer reviewer
            "first_peer_reviewer": self.first_peer_reviewer.to_compact()
            if self.first_peer_reviewer
            else None,
            "source_link": self.source_link or None,
            "sensitive_data": getattr(self, "sensitive_data"),
            "comments": self.comments or None,
            "sources": sources_json,
            "labels": labels_json,
            "verLabels": ver_labels_json,
            "events": events_json,
            "social_media_handles": handles_json,
            "sanction_regimes": regimes_json,
            "sub_type": self.sub_type.to_dict() if self.sub_type else None,
            "aliases": aliases_json,
            "medias": medias_json,
            "actor_relations": actor_relations_dict,
            "bulletin_relations": bulletin_relations_dict,
            "incident_relations": incident_relations_dict,
            "organization_relations": organization_relations_dict,
            "birth_place": self.birth_place.to_dict() if self.birth_place else None,
            "residence_place": self.residence_place.to_dict()
            if self.residence_place
            else None,
            "origin_place": self.origin_place.to_dict() if self.origin_place else None,

            "birth_date": DateHelper.serialize_datetime(self.birth_date) if self.birth_date else None,
            "publish_date": DateHelper.serialize_datetime(self.publish_date),
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "status": self.status,
            "review": self.review if self.review else None,
            "review_action": self.review_action if self.review_action else None,
            "updated_at": DateHelper.serialize_datetime(self.get_modified_date()),
            "roles": [role.to_dict() for role in self.roles] if self.roles else []
        }

        # handle missing actors mode
        if cfg.MISSING_PERSONS:
            mp = self.mp_json()
            actor.update(mp)

        return actor

    def to_mode2(self):

        # Sources json
        sources_json = []
        if self.sources and len(self.sources):
            for source in self.sources:
                sources_json.append({"id": source.id, "title": source.title})

        return {
            "class": "Actor",
            "id": self.id,
            "originid": self.originid or None,
            "name": self.name or None,
            "description": self.description or None,
            "credibility": self.credibility or None,
            "comments": self.comments or None,
            "sources": sources_json,
            "publish_date": DateHelper.serialize_datetime(self.publish_date),
            "documentation_date": DateHelper.serialize_datetime(self.documentation_date),
            "status": self.status if self.status else None,

        }

    def to_json(self, export=False):
        actor_to_dict = self.to_dict()
        if export:
            actor_to_dict = export_json_rename_handler(actor_to_dict)
        return json.dumps(actor_to_dict)

    @staticmethod
    def geo_query_origin_place(target_point, radius_in_meters):
        """Condition for direct association between actor and origin_place."""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)
        return Actor.id.in_(
            db.session.query(Actor.id)
            .join(Location, Actor.origin_place_id == Location.id)
            .filter(func.ST_DWithin(
                func.cast(Location.geometry, Geography),
                func.cast(point, Geography),
                radius_in_meters))
        )

    @staticmethod
    def geo_query_birth_place(target_point, radius_in_meters):
        """Condition for direct association between actor and birth_place."""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)
        return Actor.id.in_(
            db.session.query(Actor.id)
            .join(Location, Actor.birth_place_id == Location.id)
            .filter(func.ST_DWithin(
                func.cast(Location.geometry, Geography),
                func.cast(point, Geography),
                radius_in_meters))
        )

    @staticmethod
    def geo_query_residence_place(target_point, radius_in_meters):
        """Condition for direct association between actor and residence_place."""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)
        return Actor.id.in_(
            db.session.query(Actor.id)
            .join(Location, Actor.residence_place_id == Location.id)
            .filter(func.ST_DWithin(
                func.cast(Location.geometry, Geography),
                func.cast(point, Geography),
                radius_in_meters))
        )

    @staticmethod
    def geo_query_event_location(target_point, radius_in_meters):
        """Condition for association between actor and location via events."""
        point = func.ST_SetSRID(func.ST_MakePoint(target_point.get('lng'), target_point.get('lat')), 4326)

        conditions = []
        conditions.append(
            Actor.id.in_(
                db.session.query(actor_events.c.actor_id)
                .join(Event, actor_events.c.event_id == Event.id)
                .join(Location, Event.location_id == Location.id)
                .filter(func.ST_DWithin(
                    func.cast(Location.geometry, Geography),
                    func.cast(point, Geography),
                    radius_in_meters))))
        conditions.append(
            Actor.id.in_(
                db.session.query(actor_events.c.actor_id)
                .join(Event, actor_events.c.event_id == Event.id)
                .join(GeoLocation, Event.geo_location_id == GeoLocation.id)
                .filter(func.ST_DWithin(
                    func.cast(GeoLocation.geometry, Geography),
                    func.cast(point, Geography),
                    radius_in_meters))))
        return or_(*conditions)

    def validate(self):
        """
        a helper method to validate actors upon setting values from CSV row, invalid actors can be dropped.
        :return:
        """
        if not self.name:
            return False
        return True


class Alias(db.Model, BaseMixin):
    """
    Alias for actors
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    name_ar = db.Column(db.String, nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('actor.id'), nullable=False)
    actor = db.relationship('Actor', back_populates='aliases')

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "name_ar": self.name_ar,
            "actor_id": self.actor_id
        }

    def from_json(self, jsn):
        self.name = jsn.get('name', self.name)
        self.name_ar = jsn.get('name_ar', self.name_ar)
        if 'actor_id' in jsn:
            self.actor_id = jsn['actor_id']
        elif 'actor' in jsn:
            self.actor_id = jsn['actor']['id']
        return self


# Incident to bulletin uni-direction relation
class Itob(db.Model, BaseMixin):
    """
    Incident to bulletin relations model
    """
    extend_existing = True

    # Available Backref: incident
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), primary_key=True)

    # Available Backref: bulletin
    bulletin_id = db.Column(db.Integer, db.ForeignKey("bulletin.id"), primary_key=True)

    # Relationship extra fields
    related_as = db.Column(db.Integer)
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_itobs", foreign_keys=[user_id])

    @property
    def relation_info(self):
        related_info = ItobInfo.query.filter(ItobInfo.id == self.related_as).first() if self.related_as else None
        # Return the to_dict representation of the related_info if it exists, or an empty dictionary if not
        return related_info.to_dict() if related_info else {}

    # custom serialization method
    def to_dict(self):

        return {
            "bulletin": self.bulletin.to_compact(),
            "incident": self.incident.to_compact(),
            "related_as": self.related_as,
            "probability": self.probability,
            "comment": self.comment,
            "user_id": self.user_id,
        }

    # this will update only relationship data
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class ItobInfo(db.Model, BaseMixin):
    """
    Itob Relation Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


# Incident to actor uni-direction relation
class Itoa(db.Model, BaseMixin):
    """
    Incident to actor relationship model
    """
    extend_existing = True

    # Available Backref: actor
    actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"), primary_key=True)

    # Available Backref: incident
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), primary_key=True)

    # Relationship extra fields
    related_as = db.Column(ARRAY(db.Integer))
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_itoas", foreign_keys=[user_id])

    @property
    def relation_info(self):
        # Query the AtobInfo table based on the related_as list
        related_infos = ItoaInfo.query.filter(ItoaInfo.id.in_(self.related_as)).all() if self.related_as else []
        # Return the to_dict representation of each of them
        return [info.to_dict() for info in related_infos]

    # custom serialization method
    def to_dict(self):

        return {
            "actor": self.actor.to_compact(),
            "incident": self.incident.to_compact(),
            "related_as": self.related_as,
            "probability": self.probability,
            "comment": self.comment,
            "user_id": self.user_id,
        }

    # this will update only relationship data, (populates it from json dict)
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class ItoaInfo(db.Model, BaseMixin):
    """
    Itoa Relation Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


# incident to incident relationship
class Itoi(db.Model, BaseMixin):
    """
    Incident to incident relation model
    """
    extend_existing = True

    # This constraint will make sure only one relationship exists across bulletins (and prevent self relation)
    __table_args__ = (db.CheckConstraint("incident_id < related_incident_id"),)

    # Source Incident
    # Available Backref: incident_from
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), primary_key=True)

    # Target Incident
    # Available Backref: Incident_to
    related_incident_id = db.Column(
        db.Integer, db.ForeignKey("incident.id"), primary_key=True
    )

    # Relationship extra fields
    related_as = db.Column(db.Integer)
    probability = db.Column(db.Integer)
    comment = db.Column(db.Text)

    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_itois", foreign_keys=[user_id])

    @property
    def relation_info(self):
        related_info = ItoiInfo.query.filter(ItoiInfo.id == self.related_as).first() if self.related_as else None
        # Return the to_dict representation of the related_info if it exists, or an empty dictionary if not
        return related_info.to_dict() if related_info else {}

    # Check if two incidents are related , if so return the relation, otherwise false
    @staticmethod
    def are_related(a_id, b_id):

        if a_id == b_id:
            return False

        # with our id constraint set, just check if there is relation from the lower id to the upper id
        f, t = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        relation = Itoi.query.get((f, t))
        if relation:
            return relation
        else:
            return False

    # Give an id, get the other bulletin id (relating in or out)
    def get_other_id(self, id):
        if id in (self.incident_id, self.related_incident_id):
            return (
                self.incident_id
                if id == self.related_incident_id
                else self.related_incident_id
            )
        return None

    # Create and return a relation between two bulletins making sure the relation goes from the lower id to the upper id
    @staticmethod
    def relate(a, b):
        f, t = min(a.id, b.id), max(a.id, b.id)
        return Itoi(incident_id=f, related_incident_id=t)

    # custom serialization method
    @check_relation_roles
    def to_dict(self, exclude=None):
        if not exclude:
            return {
                "incident_from": self.incident_from.to_compact(),
                "incident_to": self.incident_to.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }
        else:
            incident = (
                self.incident_to
                if exclude == self.incident_from
                else self.incident_from
            )
            return {
                "incident": incident.to_compact(),
                "related_as": self.related_as,
                "probability": self.probability,
                "comment": self.comment,
                "user_id": self.user_id,
            }

    # this will update only relationship data
    def from_json(self, relation=None):
        if relation:
            self.probability = (
                relation["probability"] if "probability" in relation else None
            )
            self.related_as = (
                relation["related_as"] if "related_as" in relation else None
            )
            self.comment = relation["comment"] if "comment" in relation else None
            print("Relation has been updated.")
        else:
            print("Relation was not updated.")
        return self


class ItoiInfo(db.Model, BaseMixin):
    """
    Itoi Information Model
    """
    extend_existing = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    reverse_title = db.Column(db.String, nullable=True)
    title_tr = db.Column(db.String)
    reverse_title_tr = db.Column(db.String)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reverse_title": self.reverse_title,
            "title_tr": self.title_tr,
            "reverse_title_tr": self.reverse_title_tr
        }

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.reverse_title = jsn.get('reverse_title', self.reverse_title)
        self.title_tr = jsn.get('title_tr', self.title_tr)
        self.reverse_title_tr = jsn.get('reverse_title_tr', self.reverse_title_tr)


class PotentialViolation(db.Model, BaseMixin):
    """
    SQL Alchemy model for potential violations
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String)
    title_ar = db.Column(db.String)

    # to serialize data
    def to_dict(self):
        return {"id": self.id, "title": self.title}

    def to_json(self):
        return json.dumps(self.to_dict())

    # load from json dit
    def from_json(self, json):
        self.title = json["title"]
        return self

    # import csv data in to db items
    @staticmethod
    def import_csv(file_storage):
        tmp = NamedTemporaryFile().name
        file_storage.save(tmp)
        df = pd.read_csv(tmp)
        df.title_ar = df.title_ar.fillna("")
        db.session.bulk_insert_mappings(PotentialViolation, df.to_dict(orient="records"))
        db.session.commit()

        # reset id sequence counter
        max_id = db.session.execute("select max(id)+1  from potential_violation").scalar()
        db.session.execute(
            "alter sequence potential_violation_id_seq restart with :m", {'m': max_id})
        db.session.commit()
        print("Potential Violation ID counter updated.")
        return ""


class ClaimedViolation(db.Model, BaseMixin):
    """
    SQL Alchemy model for claimed violations
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String)
    title_ar = db.Column(db.String)

    # serialize
    def to_dict(self):
        return {"id": self.id, "title": self.title}

    def to_json(self):
        return json.dumps(self.to_dict())

    # populate from json dict
    def from_json(self, json):
        self.title = json["title"]
        return self

    # import csv data into db items
    @staticmethod
    def import_csv(file_storage):
        tmp = NamedTemporaryFile().name
        file_storage.save(tmp)
        df = pd.read_csv(tmp)
        df.title_ar = df.title_ar.fillna("")
        db.session.bulk_insert_mappings(ClaimedViolation, df.to_dict(orient="records"))
        db.session.commit()

        # reset id sequence counter
        max_id = db.session.execute("select max(id)+1  from claimed_violation").scalar()
        db.session.execute(
            "alter sequence claimed_violation_id_seq restart with :m", {'m': max_id})
        db.session.commit()
        print("Claimed Violation ID counter updated.")
        return ""


# joint table
incident_locations = db.Table(
    "incident_locations",
    db.Column(
        "location_id", db.Integer, db.ForeignKey("location.id"), primary_key=True
    ),
    db.Column(
        "incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True
    ),
)

# joint table
incident_labels = db.Table(
    "incident_labels",
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
    db.Column(
        "incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True
    ),
)

# joint table
incident_events = db.Table(
    "incident_events",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column(
        "incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True
    ),
)

# joint table
incident_potential_violations = db.Table(
    "incident_potential_violations",
    db.Column("potentialviolation_id", db.Integer, db.ForeignKey("potential_violation.id"), primary_key=True),
    db.Column(
        "incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True
    ),
)

# joint table
incident_claimed_violations = db.Table(
    "incident_claimed_violations",
    db.Column("claimedviolation_id", db.Integer, db.ForeignKey("claimed_violation.id"), primary_key=True),
    db.Column(
        "incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True
    ),
)

# joint table
incident_roles = db.Table(
    "incident_roles",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column(
        "incident_id", db.Integer, db.ForeignKey("incident.id"), primary_key=True
    ),
)


class Incident(db.Model, BaseMixin):
    """
    SQL Alchemy model for incidents
    """
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255), nullable=False)
    title_ar = db.Column(db.String(255))

    description = db.Column(db.Text)

    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    assigned_to = db.relationship(
        "User", backref="assigned_to_incidents", foreign_keys=[assigned_to_id]
    )

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_by = db.relationship(
        "User", backref="create_by_incidents", foreign_keys=[created_by_id]
    )

    first_peer_reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    second_peer_reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    first_peer_reviewer = db.relationship(
        "User", backref="first_rev_incidents", foreign_keys=[first_peer_reviewer_id]
    )
    second_peer_reviewer = db.relationship(
        "User", backref="second_rev_incidents", foreign_keys=[second_peer_reviewer_id]
    )

    labels = db.relationship(
        "Label",
        secondary=incident_labels,
        backref=db.backref("incidents", lazy="dynamic"),
    )

    potential_violations = db.relationship(
        "PotentialViolation",
        secondary=incident_potential_violations,
        backref=db.backref("incidents", lazy="dynamic"),
    )

    claimed_violations = db.relationship(
        "ClaimedViolation",
        secondary=incident_claimed_violations,
        backref=db.backref("incidents", lazy="dynamic"),
    )

    locations = db.relationship(
        "Location",
        secondary=incident_locations,
        backref=db.backref("incidents", lazy="dynamic"),
    )

    events = db.relationship(
        "Event",
        secondary=incident_events,
        backref=db.backref("incidents", lazy="dynamic"),
        order_by="Event.from_date"
    )

    roles = db.relationship(
        "Role",
        secondary=incident_roles,
        backref=db.backref("incidents", lazy="dynamic")
    )

    # Related Actors
    related_actors = db.relationship(
        "Itoa", backref="incident", foreign_keys="Itoa.incident_id"
    )

    related_organizations = db.relationship(
        "Otoi", backref="incident", foreign_keys="Otoi.incident_id"
    )

    # Related Bulletins
    related_bulletins = db.relationship(
        "Itob", backref="incident", foreign_keys="Itob.incident_id"
    )

    # Related Incidents
    # Incidents that this incident relate to ->
    incidents_to = db.relationship(
        "Itoi", backref="incident_from", foreign_keys="Itoi.incident_id"
    )

    # Incidents that relate to this <-
    incidents_from = db.relationship(
        "Itoi", backref="incident_to", foreign_keys="Itoi.related_incident_id"
    )

    status = db.Column(db.String(255))

    comments = db.Column(db.Text)
    # review fields
    review = db.Column(db.Text)
    review_action = db.Column(db.String)

    tsv = db.Column(TSVECTOR)

    search = db.Column(db.Text, db.Computed("""
             ((((((((id)::text || ' '::text) || (COALESCE(title, ''::character varying))::text) || ' '::text) ||
                (COALESCE(title_ar, ''::character varying))::text) || ' '::text) || COALESCE(regexp_replace(regexp_replace(description, E'<.*?>', '', 'g' ), E'&nbsp;', '', 'g'), ' '::text)) ||
             ' '::text) || COALESCE(comments, ''::text)
            """))

    __table_args__ = (
        db.Index('ix_incident_search', 'search', postgresql_using="gin", postgresql_ops={'search': 'gin_trgm_ops'}),
    )

    # helper method to create a revision
    def create_revision(self, user_id=None, created=None):
        if not user_id:
            user_id = getattr(current_user, 'id', 1)
        i = IncidentHistory(
            incident_id=self.id, data=self.to_dict(), user_id=user_id
        )
        if created:
            i.created_at = created
            i.updated_at = created
        i.save()
        print("created incident revision ")

    # returns all related incidents
    @property
    def incident_relations(self):
        return self.incidents_to + self.incidents_from

    # returns all related bulletins
    @property
    def bulletin_relations(self):
        return self.related_bulletins

    # returns all related actors
    @property
    def actor_relations(self):
        return self.related_actors

    # returns all related organizations
    @property
    def organization_relations(self):
        return self.related_organizations

    @property
    def actor_relations_dict(self):
        return [relation.to_dict() for relation in self.actor_relations]

    @property
    def bulletin_relations_dict(self):
        return [relation.to_dict() for relation in self.bulletin_relations]

    @property
    def incident_relations_dict(self):
        return [relation.to_dict(exclude=self) for relation in self.incident_relations]

    @property
    def organization_relations_dict(self):
        return [relation.to_dict() for relation in self.organization_relations]

    # populate model from json dict
    def from_json(self, json):
        # All text fields
        # assigned to
        if "assigned_to" in json and json["assigned_to"] and "id" in json["assigned_to"]:
            self.assigned_to_id = json["assigned_to"]["id"]

        # created by
        if "created_by" in json and json["created_by"] and "id" in json["created_by"]:
            self.created_by_id = json["created_by"]["id"]

        self.title = json["title"] if "title" in json else None
        self.title_ar = json["title_ar"] if "title_ar" in json else None

        self.description = json["description"] if "description" in json else None

        # Labels
        if "labels" in json:
            ids = [label["id"] for label in json["labels"]]
            labels = Label.query.filter(Label.id.in_(ids)).all()
            self.labels = labels

        # Locations
        if "locations" in json:
            ids = [location["id"] for location in json["locations"]]
            locations = Location.query.filter(Location.id.in_(ids)).all()
            self.locations = locations

        # Potential Violations
        if "potential_violations" in json:
            ids = [pv["id"] for pv in json["potential_violations"]]
            potential_violations = PotentialViolation.query.filter(PotentialViolation.id.in_(ids)).all()
            self.potential_violations = potential_violations

        # Claimed Violations
        if "claimed_violations" in json:
            ids = [cv["id"] for cv in json["claimed_violations"]]
            claimed_violations = ClaimedViolation.query.filter(ClaimedViolation.id.in_(ids)).all()
            self.claimed_violations = claimed_violations

        # Events
        if "events" in json:
            new_events = []
            events = json["events"]
            for event in events:
                if "id" not in event:
                    # new event
                    e = Event()
                    e = e.from_json(event)
                    e.save()
                else:
                    # event already exists, get a db instnace and update it with new data
                    e = Event.query.get(event["id"])
                    e.from_json(event)
                    e.save()
                new_events.append(e)
            self.events = new_events

        if "roles" in json:
            ids = [role["id"] for role in json["roles"]]
            roles = Role.query.filter(Role.id.in_(ids)).all()
            self.roles = roles

        # Related Actors (actor_relations)
        if "actor_relations" in json and "check_ar" in json:
            # collect related actors ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["actor_relations"]:
                actor = Actor.query.get(relation["actor"]["id"])

                # Extra (check those actors exit)

                if actor:
                    rel_ids.append(actor.id)
                    # this will update/create the relationship (will flush to db!)
                    self.relate_actor(actor, relation=relation)

                # Find out removed relations and remove them
            # just loop existing relations and remove if the destination actor not in the related ids

            for r in self.actor_relations:
                if not (r.actor_id in rel_ids):
                    rel_actor = r.actor
                    r.delete()

                    # -revision related actor
                    rel_actor.create_revision()

        # Related Organizations (organization_relations)
        if "organization_relations" in json and "check_ar" in json:
            # collect related organizations ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["organization_relations"]:
                organization = Organization.query.get(relation["organization"]["id"])

                # Extra (check those organizations exit)

                if organization:
                    rel_ids.append(organization.id)
                    # this will update/create the relationship (will flush to db!)
                    self.relate_organization(organization, relation=relation)

                # Find out removed relations and remove them
            # just loop existing relations and remove if the destination organization not in the related ids

            for r in self.organization_relations:
                if not (r.organization_id in rel_ids):
                    rel_organization = r.organization
                    r.delete()

                    # -revision related organization
                    rel_organization.create_revision()

        # Related Bulletins (bulletin_relations)
        if "bulletin_relations" in json and "check_br" in json:
            # collect related bulletin ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["bulletin_relations"]:
                bulletin = Bulletin.query.get(relation["bulletin"]["id"])

                # Extra (check those bulletins exit)
                if bulletin:
                    rel_ids.append(bulletin.id)
                    # this will update/create the relationship (will flush to db!)
                    self.relate_bulletin(bulletin, relation=relation)

            # Find out removed relations and remove them
            # just loop existing relations and remove if the destination bulletin not in the related ids
            for r in self.bulletin_relations:
                if not (r.bulletin_id in rel_ids):
                    rel_bulletin = r.bulletin
                    r.delete()

                    # -revision related bulletin
                    rel_bulletin.create_revision()

        # Related Incidnets (incident_relations)
        if "incident_relations" in json and "check_ir" in json:
            # collect related incident ids (helps with finding removed ones)
            rel_ids = []
            for relation in json["incident_relations"]:
                incident = Incident.query.get(relation["incident"]["id"])
                # Extra (check those incidents exit)

                if incident:
                    rel_ids.append(incident.id)
                    # this will update/create the relationship (will flush to db)
                    self.relate_incident(incident, relation=relation)

                # Find out removed relations and remove them
            # just loop existing relations and remove if the destination incident no in the related ids

            for r in self.incident_relations:
                # get related incident (in or out)
                rid = r.get_other_id(self.id)
                if not (rid in rel_ids):
                    r.delete()

                    # - revision related incident
                    Incident.query.get(rid).create_revision()

        if "comments" in json:
            self.comments = json["comments"]

        if "status" in json:
            self.status = json["status"]

        return self

    # Compact dict for relationships
    @check_roles
    def to_compact(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description or None,
        }

    # Helper method to handle logic of relating incidents
    def relate_incident(self, incident, relation=None, create_revision=True):

        # if a new actor is being created, we must save it to get the id
        if not self.id:
            self.save()

        # Relationships are alwasy forced to go from the lower id to the bigger id (to prevent duplicates)
        # Enough to look up the relationship from the lower to the upper

        # reject self relation
        if self == incident:
            return

        existing_relation = Itoi.are_related(self.id, incident.id)
        if existing_relation:
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation (possible from or to the actor based on the id comparison)
            new_relation = Itoi.relate(self, incident)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # -revision related incident
            if create_revision:
                incident.create_revision()

    # Helper method to handle logic of relating actors
    def relate_actor(self, actor, relation=None, create_revision=True):
        # if current incident is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (actor_id, incident_id)
        existing_relation = Itoa.query.get((actor.id, self.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Itoa(incident_id=self.id, actor_id=actor.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # -revision related actor
            if create_revision:
                actor.create_revision()

    # Helper method to handle logic of relating bulletins
    def relate_bulletin(self, bulletin, relation=None, create_revision=True):
        # if current incident is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (incident_id,bulletin_id)
        existing_relation = Itob.query.get((self.id, bulletin.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Itob(incident_id=self.id, bulletin_id=bulletin.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # -revision related bulletin
            if create_revision:
                bulletin.create_revision()

    # Helper method to handle logic of relating actors
    def relate_organization(self, organization, relation=None, create_revision=True):
        # if current incident is new, save it to get the id
        if not self.id:
            self.save()

        # query order : (organization_id, incident_id)
        existing_relation = Otoi.query.get((organization.id, self.id))

        if existing_relation:
            # Relationship exists :: Updating the attributes
            existing_relation.from_json(relation)
            existing_relation.save()

        else:
            # Create new relation
            new_relation = Otoi(incident_id=self.id, organization_id=organization.id)
            # update relation data
            new_relation.from_json(relation)
            new_relation.save()

            # -revision related organization
            if create_revision:
                organization.create_revision()

    @check_roles
    def to_dict(self, mode=None):

        # Try to detect a user session
        if current_user:
            if not current_user.can_access(self):
                return self.restricted_json()

        if mode == '1':
            return self.min_json()
        if mode == '2':
            return self.to_mode2()

        # Labels json
        labels_json = []
        if self.labels and len(self.labels):
            for label in self.labels:
                labels_json.append({"id": label.id, "title": label.title})

        # Locations json
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.to_compact())

        # potential violations json
        pv_json = []
        if self.potential_violations and len(self.potential_violations):
            for pv in self.potential_violations:
                pv_json.append({"id": pv.id, "title": pv.title})

        # claimed violations json
        cv_json = []
        if self.claimed_violations and len(self.claimed_violations):
            for cv in self.claimed_violations:
                cv_json.append({"id": cv.id, "title": cv.title})

        # Events json
        events_json = []
        if self.events and len(self.events):
            for event in self.events:
                events_json.append(event.to_dict())

        bulletin_relations_dict = []
        actor_relations_dict = []
        incident_relations_dict = []
        organization_relations_dict = []

        if str(mode) != '3':
            # lazy load if mode is 3
            for relation in self.bulletin_relations:
                bulletin_relations_dict.append(relation.to_dict())

            for relation in self.actor_relations:
                actor_relations_dict.append(relation.to_dict())

            for relation in self.organization_relations:
                organization_relations_dict.append(relation.to_dict())

            for relation in self.incident_relations:
                incident_relations_dict.append(relation.to_dict(exclude=self))

        return {
            "class": self.__tablename__,
            "id": self.id,
            "title": self.title or None,
            "title_ar": self.title_ar or None,
            "description": self.description or None,
            # assigned to
            "assigned_to": self.assigned_to.to_compact() if self.assigned_to else None,
            "created_by": self.created_by.to_compact() if self.created_by else None,
            # first peer reviewer
            "first_peer_reviewer": self.first_peer_reviewer.to_compact()
            if self.first_peer_reviewer
            else None,
            "labels": labels_json,
            "locations": locations_json,
            "potential_violations": pv_json,
            "claimed_violations": cv_json,
            "events": events_json,
            "actor_relations": actor_relations_dict,
            "organization_relations": organization_relations_dict,
            "bulletin_relations": bulletin_relations_dict,
            "incident_relations": incident_relations_dict,
            "comments": self.comments if self.comments else None,
            "status": self.status if self.status else None,
            "review": self.review if self.review else None,
            "review_action": self.review_action if self.review_action else None,
            "updated_at": DateHelper.serialize_datetime(self.get_modified_date()),
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "roles": [role.to_dict() for role in self.roles] if self.roles else []
        }

    # custom serialization mode
    def to_mode2(self):

        # Labels json
        labels_json = []
        if self.labels and len(self.labels):
            for label in self.labels:
                labels_json.append({"id": label.id, "title": label.title})

        # Locations json
        locations_json = []
        if self.locations and len(self.locations):
            for location in self.locations:
                locations_json.append(location.min_json())

        return {
            "class": "Incident",
            "id": self.id,
            "title": self.title or None,
            "description": self.description or None,
            "labels": labels_json,
            "locations": locations_json,
            "comments": self.comments if self.comments else None,
            "status": self.status if self.status else None,
        }

    def to_json(self, export=False):
        incident_to_dict = self.to_dict()
        if export:
            incident_to_dict = export_json_rename_handler(incident_to_dict)
        return json.dumps(incident_to_dict)

    def get_modified_date(self):
        if self.history:
            return self.history[-1].updated_at
        else:
            return self.updated_at


# ----------------------------------- History Tables (Versioning) ------------------------------------


class BulletinHistory(db.Model, BaseMixin):
    """
    SQL Alchemy model for bulletin revisions
    """
    id = db.Column(db.Integer, primary_key=True)
    bulletin_id = db.Column(db.Integer, db.ForeignKey("bulletin.id"), index=True)
    bulletin = db.relationship(
        "Bulletin", backref=db.backref("history", order_by='BulletinHistory.updated_at'), foreign_keys=[bulletin_id]
    )
    data = db.Column(JSON)
    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="bulletin_revisions", foreign_keys=[user_id])

    # serialize
    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "user": self.user.to_compact() if self.user else None,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True)

    def __repr__(self):
        return '<BulletinHistory {} -- Target {}>'.format(self.id, self.bulletin_id)


# --------------------------------- Actors History + Indexers -------------------------------------


class ActorHistory(db.Model, BaseMixin):
    """
    SQL Alchemy model for actor revisions
    """
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"), index=True)
    actor = db.relationship("Actor", backref=db.backref("history", order_by='ActorHistory.updated_at'),
                            foreign_keys=[actor_id])
    data = db.Column(JSON)
    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="actor_revisions", foreign_keys=[user_id])

    # serialize
    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "user": self.user.to_compact() if self.user else None,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True)


# --------------------------------- Incident History + Indexers -------------------------------------


class IncidentHistory(db.Model, BaseMixin):
    """
    SQL Alchemy model for incident revisions
    """
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), index=True)
    incident = db.relationship(
        "Incident", backref=db.backref("history", order_by='IncidentHistory.updated_at'), foreign_keys=[incident_id]
    )
    data = db.Column(JSON)
    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="incident_revisions", foreign_keys=[user_id])

    # serialize
    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "user": self.user.to_compact() if self.user else None,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True)


class LocationHistory(db.Model, BaseMixin):
    """
    SQL Alchemy model for location revisions
    """
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"), index=True)
    location = db.relationship(
        "Location", backref=db.backref("history", order_by='LocationHistory.updated_at'), foreign_keys=[location_id]
    )
    data = db.Column(JSON)
    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="location_revisions", foreign_keys=[user_id])

    # serialize
    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "user": self.user.to_compact() if self.user else None,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True)

    def __repr__(self):
        return '<LocationHistory {} -- Target {}>'.format(self.id, self.location_id)

class OrganizationHistory(db.Model, BaseMixin):
    """
    SQL Alchemy model for organization revisions
    """
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), index=True)
    organization = db.relationship(
        "Organization", backref=db.backref("history", order_by='OrganizationHistory.updated_at'), foreign_keys=[organization_id]
    )
    data = db.Column(JSON)
    # user tracking
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="organization_revisions", foreign_keys=[user_id])

    # serialize
    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "user": self.user.to_compact() if self.user else None,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True)

    def __repr__(self):
        return '<OrganizationHistory {} -- Target {}>'.format(self.id, self.organization_id)


class Activity(db.Model, BaseMixin):
    """
    SQL Alchemy model for activity
    """

    ACTION_UPDATE = 'UPDATE'
    ACTION_DELETE = 'DELETE'
    ACTION_CREATE = 'CREATE-REVISION'
    ACTION_BULK_UPDATE = "BULK-UPDATE"
    ACTION_APPROVE_EXPORT = "APPROVE-EXPORT"
    ACTION_REJECT_EXPORT = "REJECT-EXPORT"
    ACTION_DOWNLOAD = "DOWNLOAD"
    ACTION_LOGIN = 'LOGIN'
    ACTION_LOGOUT = 'LOGOUT'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    action = db.Column(db.String(100))
    subject = db.Column(JSON)
    tag = db.Column(db.String(100))

    # serialize data
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'subject': self.subject,
            'tag': self.tag,
            'created_at': DateHelper.serialize_datetime(self.created_at),

        }

    # helper static method to create different type of activities (tags)
    @staticmethod
    def create(user, action, subject, tag):
        try:
            activity = Activity()
            activity.user_id = user.id
            activity.action = action
            activity.subject = subject
            activity.tag = tag
            activity.save()

        except Exception:
            print('Oh Noes! Error creating activity.')


class Settings(db.Model, BaseMixin):
    """ User Specific Settings. (SQL Alchemy model)"""
    id = db.Column(db.Integer, primary_key=True)
    darkmode = db.Column(db.Boolean, default=False)


class Query(db.Model, BaseMixin):
    """
    SQL Alchemy model for saved searches
    """

    TYPES = [Bulletin.__tablename__, Actor.__tablename__, Incident.__tablename__, Organization.__tablename__]

    __table_args__ = (db.UniqueConstraint("user_id", "name", name="unique_user_queryname"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship("User", backref="queries", foreign_keys=[user_id])
    data = db.Column(JSON)
    query_type = db.Column(db.String, nullable=False, default=Bulletin.__tablename__)

    # serialize data
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'data': self.data,
            'query_type': self.query_type
        }

    def to_json(self):
        return json.dumps(self.to_dict())


class Country(db.Model, BaseMixin):
    """
    SQL Alchemy model for countries
    """
    __tablename__ = 'countries'
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    title_tr = db.Column(db.String)

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.title_tr = jsn.get('title_tr', self.title_tr)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'title_tr': self.title_tr,
            'created_at': DateHelper.serialize_datetime(self.created_at),
            'updated_at': DateHelper.serialize_datetime(self.updated_at)
        }

    @staticmethod
    def find_by_title(title):
        country = Country.query.filter(Country.title_tr.ilike(title)).first()
        if country:
            return country
        else:
            return Country.query.filter(Country.title.ilike(title)).first()



class Ethnography(db.Model, BaseMixin):
    """
    SQL Alchemy model for ethnographies
    """
    __tablename__ = 'ethnographies'
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    title_tr = db.Column(db.String)

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.title_tr = jsn.get('title_tr', self.title_tr)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'title_tr': self.title_tr,
            'created_at': DateHelper.serialize_datetime(self.created_at),
            'updated_at': DateHelper.serialize_datetime(self.updated_at)
        }

    @staticmethod
    def find_by_title(title):
        ethnography = Ethnography.query.filter(Ethnography.title_tr.ilike(title)).first()
        if ethnography:
            return ethnography
        else:
            return Ethnography.query.filter(Ethnography.title.ilike(title)).first()


class AppConfig(db.Model, BaseMixin):
    """Global Application Settings. (SQL Alchemy model)"""
    id = db.Column(db.Integer, primary_key=True)
    config = db.Column(JSON, nullable=False)

    # add user reference
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_configs", foreign_keys=[user_id])

    def to_dict(self):
        print(self.user)
        return {
            'id': self.id,
            'config': self.config,
            'created_at': DateHelper.serialize_datetime(self.created_at),
            'user': self.user.to_dict() if self.user else {}

        }


class MediaCategory(db.Model, BaseMixin):
    """
    SQL Alchemy model for media categories
    """
    __tablename__ = 'media_categories'
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    title_tr = db.Column(db.String)

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.title_tr = jsn.get('title_tr', self.title_tr)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'title_tr': self.title_tr,
            'created_at': DateHelper.serialize_datetime(self.created_at),
            'updated_at': DateHelper.serialize_datetime(self.updated_at)
        }


class GeoLocationType(db.Model, BaseMixin):
    """
    SQL Alchemy model for geo location types
    """
    __tablename__ = 'geo_location_types'
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    title_tr = db.Column(db.String)

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.title_tr = jsn.get('title_tr', self.title_tr)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'title_tr': self.title_tr,
            'created_at': DateHelper.serialize_datetime(self.created_at),
            'updated_at': DateHelper.serialize_datetime(self.updated_at)
        }


class WorkflowStatus(db.Model, BaseMixin):
    """
    SQL Alchemy model for workflow statuses
    """
    __tablename__ = 'workflow_statuses'
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    title_tr = db.Column(db.String)

    def from_json(self, jsn):
        self.title = jsn.get('title', self.title)
        self.title_tr = jsn.get('title_tr', self.title_tr)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'title_tr': self.title_tr,
            'created_at': DateHelper.serialize_datetime(self.created_at),
            'updated_at': DateHelper.serialize_datetime(self.updated_at)
        }
