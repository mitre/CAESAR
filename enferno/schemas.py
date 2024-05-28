from enferno.user.models import User, Role
from enferno.admin.models import (Bulletin, Label, Source, Location, Eventtype, Media, Actor, Incident,
                                  IncidentHistory, BulletinHistory, ActorHistory, LocationHistory, PotentialViolation,
                                  ClaimedViolation,
                                  Activity, Query, LocationAdminLevel, LocationType, AppConfig,
                                  AtobInfo, AtoaInfo, BtobInfo, ItoiInfo, ItoaInfo, ItobInfo, Country, Ethnography,
                                  MediaCategory, GeoLocationType, WorkflowStatus)
from sqlalchemy.dialects.postgresql import TSVECTOR
from geoalchemy2.types import Geometry
from marshmallow import fields as marsmallow_fields, EXCLUDE, INCLUDE
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema, ModelConverter

#https://stackoverflow.com/questions/71720473/getting-foreign-key-instead-of-relationship-table-in-marshmallow-sqlalchemy-sche
#https://github.com/marshmallow-code/marshmallow-sqlalchemy/issues/182
#https://readthedocs.org/projects/marshmallow-sqlalchemy/downloads/pdf/dev/

# The TSVector type is not available in the default marsmallow
# https://github.com/marshmallow-code/marshmallow-sqlalchemy/issues/42
# see https://github.com/marshmallow-code/marshmallow-sqlalchemy/issues/27
class Converter(ModelConverter):
    SQLA_TYPE_MAPPING = dict(
        list(ModelConverter.SQLA_TYPE_MAPPING.items()) +
        [(TSVECTOR, marsmallow_fields.Raw)] +
        [(Geometry, marsmallow_fields.String)]
    )

class BaseSchema(SQLAlchemyAutoSchema):
    class Meta:
        model_converter = Converter
        include_relationships = False
        include_fk = True
        transient = True
        load_instance = True

class UserSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=User

class RoleSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Role

class BulletinSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model = Bulletin
        #### unknown and exclude can be useful in tailoring input validation. We don't currently use schemas for input validation
        # unknown = EXCLUDE # not a strict validation 
                            # JSON elements that are not in the SQLAlchemy model will not be validated but can still be pulled
                            # from the message body and processed by the Flask view code.
        # exclude = ("publish_date", ) # validation doesn't accept an empty string JSON value for the publish date
                                        # currently our client code sends an JSON object with this value set as an empty string 
                                        # this 'exclude' setting means that publish_data does not appear in generated docs

class LabelSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Label

class SourceSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Source

class LocationSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Location

class EventtypeSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Eventtype

class MediaSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Media

class ActorSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Actor

class IncidentSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Incident

class IncidentHistorySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=IncidentHistory

class ActorHistorySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=ActorHistory

class BulletinHistorySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=BulletinHistory

class LocationHistorySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=LocationHistory

class PotentialViolationSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=PotentialViolation

class ClaimedViolationSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=ClaimedViolation

class ActivitySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Activity

class QuerySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Query

class LocationAdminLevelSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=LocationAdminLevel

class LocationTypeSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=LocationType

class AppConfigSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=AppConfig

class MediaCategorySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=MediaCategory

class GeoLocationTypeSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=GeoLocationType

class WorkflowStatusSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=WorkflowStatus

class EthnographySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Ethnography

class AtobInfoSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=AtobInfo

class AtoaInfoSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=AtoaInfo

class BtobInfoSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=BtobInfo

class ItoiInfoSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=ItoiInfo

class ItoaInfoSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=ItoaInfo

class ItobInfoSchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=ItobInfo

class CountrySchema(SQLAlchemyAutoSchema):
    class Meta(BaseSchema.Meta):
        model=Country

# code to add SqlAlchemy models to the OpenAPI spec as components without associating them to any API endpoint
# https://github.com/apiflask/apiflask/blob/a9bb0585b6a9164c82a1da5fbe4e42e575d497c0/docs/openapi.md?plain=1#L1144
def add_sqlalchemy_models(spec):
    spec.components.schema('SqlAlchemy_User', schema=UserSchema)
    spec.components.schema('SqlAlchemy_Role', schema=RoleSchema)
    spec.components.schema('SqlAlchemy_Bulletin', schema=BulletinSchema)
    spec.components.schema('SqlAlchemy_Label', schema=LabelSchema)
    spec.components.schema('SqlAlchemy_Source', schema=SourceSchema)
    spec.components.schema('SqlAlchemy_Location', schema=LocationSchema)
    spec.components.schema('SqlAlchemy_Eventtype', schema=EventtypeSchema)
    spec.components.schema('SqlAlchemy_Media', schema=MediaSchema)
    spec.components.schema('SqlAlchemy_Actor', schema=ActorSchema)
    spec.components.schema('SqlAlchemy_Incident', schema=IncidentSchema)
    spec.components.schema('SqlAlchemy_IncidentHistory', schema=IncidentHistorySchema)
    spec.components.schema('SqlAlchemy_BulletinHistory', schema=BulletinHistorySchema)
    spec.components.schema('SqlAlchemy_ActorHistory', schema=ActorHistorySchema)
    spec.components.schema('SqlAlchemy_LocationHistory', schema=LocationHistorySchema)
    spec.components.schema('SqlAlchemy_PotentialViolation', schema=PotentialViolationSchema)
    spec.components.schema('SqlAlchemy_ClaimedViolation', schema=ClaimedViolationSchema)
    spec.components.schema('SqlAlchemy_Activity', schema=ActivitySchema)
    spec.components.schema('SqlAlchemy_Query', schema=LocationAdminLevelSchema)
    spec.components.schema('SqlAlchemy_LocationType', schema=LocationTypeSchema)
    spec.components.schema('SqlAlchemy_AppConfig', schema=AppConfigSchema)
    spec.components.schema('SqlAlchemy_AtobInfo', schema=AtobInfoSchema)
    spec.components.schema('SqlAlchemy_AtoaInfo', schema=AtoaInfoSchema)
    spec.components.schema('SqlAlchemy_BtobInfo', schema=BtobInfoSchema)
    spec.components.schema('SqlAlchemy_ItoiInfo', schema=ItoiInfoSchema)
    spec.components.schema('SqlAlchemy_ItoaInfo', schema=ItoaInfoSchema)
    spec.components.schema('SqlAlchemy_ItobInfo', schema=ItobInfoSchema)
    spec.components.schema('SqlAlchemy_Country', schema=CountrySchema)
    spec.components.schema('SqlAlchemy_Ethnography', schema=EthnographySchema)
    spec.components.schema('SqlAlchemy_MediaCategory', schema=MediaCategorySchema)
    spec.components.schema('SqlAlchemy_GeoLocationType', schema=GeoLocationTypeSchema)
    spec.components.schema('SqlAlchemy_WorkflowStatus', schema=WorkflowStatusSchema)
    return spec