import os
from enferno.app import create_app
from enferno.settings import Config
from enferno.schemas import add_sqlalchemy_models

config = Config()
app = create_app(config)

# display documentation of SQL alchemy models in the API documentation when deploying in a development environment
if config.ENV == 'dev':
    app.config['SPEC_PROCESSOR_PASS_OBJECT'] = True
    app.spec_callback = add_sqlalchemy_models