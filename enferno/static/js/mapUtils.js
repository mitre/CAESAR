class MapUtils {

    constructor() {}

    loadBaseLayer() {
        return new Promise((resolve, reject) => {
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
                        resolve(rasterStyle);
                    }
                    reject("unsupported endpoint");
                } else {  
                    // expecting url to mapbox style json
                    fetch(mapsApiEndpoint).then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP error! Status: ${response.status}`);
                        }
                        return response.json();
                    }).then(data => resolve(data)).catch(error => reject(error));
                }
            }
        });
    }

    getFeatureBounds(polygons) {
        const turfBounds = turf.bbox(polygons);
        return turfBounds;
    }
}

const mapUtils = new MapUtils();