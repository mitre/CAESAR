import os

from datetime import datetime as dt, timedelta
from pathlib import Path

import arrow
from sqlalchemy import ARRAY
from flask import current_app
from flask_security.decorators import current_user
from sqlalchemy.ext.declarative import declared_attr

from enferno.extensions import db
from enferno.settings import Config as cfg

from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from itsdangerous import URLSafeSerializer

class BaseExport(db.Model, BaseMixin):
    __abstract__ = True
    export_dir = Path("enferno/exports")
    export_file_name = "export"
    signer = URLSafeSerializer(cfg.SECRET_KEY)
    """
    model for export tables
    """
    @declared_attr
    def requester_id(cls):
        return db.Column(db.Integer, db.ForeignKey("user.id"))

    @declared_attr
    def requester(cls):
        if cls.__tablename__ == 'group_export':
            return db.relationship("User", backref="group_exports", foreign_keys=[cls.requester_id])
        return db.relationship("User", backref="user_exports", foreign_keys=[cls.requester_id])
    file_format = db.Column(db.String, nullable=False)
    include_media = db.Column(db.Boolean, default=False)
    file_id = db.Column(db.String)
    ref = db.Column(ARRAY(db.String))
    comment = db.Column(db.Text)
    status = db.Column(db.String, nullable=False, default='Pending')
    @declared_attr
    def approver_id(cls):
        return db.Column(db.Integer, db.ForeignKey("user.id"))

    @declared_attr
    def approver(cls):
        if cls.__tablename__ == 'group_export':
            return db.relationship("User", backref="group_approved_exports", foreign_keys=[cls.approver_id])
        return db.relationship("User", backref="approved_exports", foreign_keys=[cls.approver_id])
    expires_on = db.Column(db.DateTime)


    @property
    def unique_id(self):
        return BaseExport.signer.dumps(self.id)

    @staticmethod
    def decrypt_unique_id(key):
        """
        :param key: unique
        :return: export request id
        """
        return BaseExport.signer.loads(key)

    @property
    def expired(self):
        if self.expires_on:
            return dt.utcnow() > self.expires_on
        else:
            return True
    
    def approve(self):
        """
        Method to approve Export requests.
        """
        self.status = 'Processing'
        # set download expiry
        self.expires_on = dt.utcnow() + timedelta(
            seconds=current_app.config.get('EXPORT_DEFAULT_EXPIRY'))
        self.approver = current_user

        return self
    
    def reject(self):
        """
        Method to reject Export requests.
        """
        self.status = 'Rejected'

        return self
    
    def set_expiry(self, date):
        """
        Method to change expiry date/time
        """
        try:
            expires_on = arrow.get(date)
        except Exception as e:
            print(F"Error saving export #{self.id}: \n {e}")

        if expires_on > arrow.utcnow():
            self.expires_on = expires_on.format('YYYY-MM-DDTHH:mm')
        
        return self

    @staticmethod
    def generate_export_dir():
        """
        Static method to generate export directory
        :return: export directory
        """
        dir_id = f'export_{dt.utcnow().strftime("%Y%m%d-%H%M%S")}'
        Path(BaseExport.export_dir / dir_id).mkdir(parents=True, exist_ok=True)
        return dir_id

    @staticmethod
    def generate_export_file():
        """
        static method to generate export file
        :return: export file path, export directory
        """
        # Create unique directory
        dir_id = BaseExport.generate_export_dir()
        return BaseExport.export_dir / dir_id / BaseExport.export_file_name, dir_id

class GroupExport(BaseExport):
    """
    model for group export table
    """
    id = db.Column(db.Integer, primary_key=True)
    items = db.relationship("GroupExportItem", back_populates="group_export")


    def from_json(self, json):
        """
        Group Export Deserializer.
        :param json: json request data
        """

        cfg = json.get('config')
        items = json.get('items')

        for item in items:
            self.items.append(GroupExportItem(item_id=item['item_id'], table=item['table']))

        self.requester = current_user
        self.ref = cfg.get('ref') if "ref" in cfg else []
        self.comment = cfg.get('comment')
        self.file_format = cfg.get('format')
        self.include_media = cfg.get('includeMedia')

        return self

    def to_dict(self):
        """
        Export Serializer.
        """
        items_json = []
        for item in self.items:
            items_json.append({
                "item_id": item.item_id,
                "table": item.table
            })
        return {
            "id": self.id,

            "class": self.__tablename__,
            "requester": self.requester.to_compact(),
            "approver": self.approver.to_compact() if self.approver else None,
            "include_media": self.include_media,
            "file_format": self.file_format,
            "status": self.status,
            "comment": self.comment,
            "ref": self.ref or None,
            "file_id": self.file_id,
            "expires_on": DateHelper.serialize_datetime(self.expires_on) if self.expires_on else None,
            "updated_at":  DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None,
            "created_at" : DateHelper.serialize_datetime(self.created_at) if self.created_at else None,
            "expired": self.expired,
            "uid": self.unique_id,
            "items": items_json,
            "table": "group"

        }


class GroupExportItem(db.Model, BaseMixin):
    id = db.Column(db.Integer, primary_key=True)
    group_export_id = db.Column(db.Integer, db.ForeignKey("group_export.id"))
    group_export = db.relationship("GroupExport", back_populates="items", foreign_keys=[group_export_id])
    item_id = db.Column(db.Integer)
    table = db.Column(db.String, nullable=False)


class Export(BaseExport):
    id = db.Column(db.Integer, primary_key=True)
    items = db.Column(ARRAY(db.Integer))
    table = db.Column(db.String, nullable=False)

        
    def from_json(self, table, json):
        """
        Export Deserializer.
        :param table: str for the table the export is for
        :param json: json request data
        """

        cfg = json.get('config')
        items = json.get('items')

        self.requester = current_user
        self.table = table
        self.items = items
        self.ref = cfg.get('ref') if "ref" in cfg else []
        self.comment = cfg.get('comment')
        self.file_format = cfg.get('format')
        self.include_media = cfg.get('includeMedia')

        return self

    def to_dict(self):
        """
        Export Serializer.
        """
        return {
            "id": self.id,

            "class": self.__tablename__,
            "table": self.table,
            "requester": self.requester.to_compact(),
            "approver": self.approver.to_compact() if self.approver else None,
            "include_media": self.include_media,
            "file_format": self.file_format,
            "status": self.status,
            "comment": self.comment,
            "ref": self.ref or None,
            "file_id": self.file_id,
            "expires_on": DateHelper.serialize_datetime(self.expires_on) if self.expires_on else None,
            "updated_at":  DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None,
            "created_at" : DateHelper.serialize_datetime(self.created_at) if self.created_at else None,
            "expired": self.expired,
            "uid": self.unique_id,
            "items": self.items,

        }

