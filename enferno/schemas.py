from enferno.user.models import User, Role
from enferno.admin.models import (Bulletin, Label, Source, Location, Eventtype, Media, Actor, Incident,
                                  IncidentHistory, BulletinHistory, ActorHistory, LocationHistory, PotentialViolation,
                                  ClaimedViolation,
                                  Activity, Query, LocationAdminLevel, LocationType, AppConfig,
                                  AtobInfo, AtoaInfo, BtobInfo, ItoiInfo, ItoaInfo, ItobInfo, Country, Ethnography,
                                  MediaCategory, GeoLocationType, WorkflowStatus)
from sqlalchemy.dialects.postgresql import TSVECTOR
from marshmallow import fields as marsmallow_fields, EXCLUDE, INCLUDE
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema, ModelConverter

# The TSVector type is not available in the default marsmallow
# https://github.com/marshmallow-code/marshmallow-sqlalchemy/issues/42
# see https://github.com/marshmallow-code/marshmallow-sqlalchemy/issues/27
class Converter(ModelConverter):
    SQLA_TYPE_MAPPING = dict(
        list(ModelConverter.SQLA_TYPE_MAPPING.items()) +
        [(TSVECTOR, marsmallow_fields.Raw)]
    )

class BaseSchema(SQLAlchemyAutoSchema):
    class Meta:
        model_converter = Converter
        include_relationships = True
        include_fk = True
        transient = True
        load_instance = True

class UserSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=User

class BulletinSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model = Bulletin
        unknown = EXCLUDE # not a strict validation 
                            # JSON elements that are not in the SQLAlchemy model will not be validated but can still be pulled
                            # from the message body and processed by the Flask view code.
        exclude = ("publish_date", ) # validation doesn't accept an empty string JSON value for the publish date
                                        # currently our client code sends an JSON object with this value set as an empty string 
                                        # this 'exclude' setting means that publish_data does not appear in generated docs 

# users = fields.Nested(UserSchema)
#https://stackoverflow.com/questions/71720473/getting-foreign-key-instead-of-relationship-table-in-marshmallow-sqlalchemy-sche
#https://github.com/marshmallow-code/marshmallow-sqlalchemy/issues/182
#https://readthedocs.org/projects/marshmallow-sqlalchemy/downloads/pdf/dev/
        