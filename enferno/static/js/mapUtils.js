class MapUtils {

    constructor() {}

    loadBaseLayer() {
        if(mapsApiEndpoint) {
            if(mapsApiEndpoint.includes("{x}")) {
                if(!mapsApiEndpoint.includes(".pbf")) {
                    const rasterStyle = {
                        'version': 8,
                        'sources': {
                            'raster': {
                                'type': 'raster',
                                "tiles": [mapsApiEndpoint],
                            }
                        },
                        'layers': [
                            {
                                "id": "baseLayer",
                                "type": "raster",
                                "source": "raster",
                                "layout": {"visibility": "visible"}
                            }
                        ],
                        "glyphs": "/static/font/{fontstack}/{range}.pbf",
                    };
                    return rasterStyle;
                }
            } else {
                return mapsApiEndpoint;
            }
        }
    }
}

const mapUtils = new MapUtils();