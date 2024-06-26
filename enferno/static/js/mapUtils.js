class MapUtils {

    constructor() {}

    // static initMap(mapOptions) {
    //     return new Promise((resolve, reject) => {
    //         const map = new maplibregl.Map(mapOptions);
    //         map.on('style.load', () => {
    //             const waiting = () => {
    //               if (!map.isStyleLoaded()) {
    //                 setTimeout(waiting, 200);
    //               } else {
    //                 resolve(map);
    //               }
    //             };
    //             waiting();
    //         });
    //     });
    // }

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

    getFeatureBounds(coordinates) {
        if (coordinates.length) {  
          var bounds = coordinates.reduce(function(bounds, coord) {
            return bounds.extend(coord);
          }, new maplibregl.LngLatBounds(coordinates[0], coordinates[0]));
          return bounds;
        }
        return null;
    }
}

const mapUtils = new MapUtils();