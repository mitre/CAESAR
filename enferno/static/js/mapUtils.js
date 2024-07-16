class MapUtils {

    constructor() { }

    loadBaseLayer() {
        return new Promise((resolve, reject) => {
            if (mapsApiEndpoint) {
                if (mapsApiEndpoint.includes("{x}")) {
                    if (!mapsApiEndpoint.includes(".pbf")) {
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
                                    "layout": { "visibility": "visible" }
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

    removeGeometryLayers(map) {
        if (map.getSource('location_geometries')) {
            map.removeLayer('location_polygon');
            map.removeLayer('location_polygon_outline');
            map.removeLayer('location_line_strings');
            map.removeLayer('location_points');
            map.removeSource('location_geometries');
        }
    }

    addGeometries(map, geometry) {
        if (!map.getSource("location_geometries")) {
            map.addSource('location_geometries', {
                'type': 'geojson',
                'data': geometry
            });
        } else {
            map.getSource('location_geometries').setData(geometry);
        }
        if (!map.getLayer("location_polygon")) {
            map.addLayer({
                'id': 'location_polygon',
                'type': 'fill',
                'source': 'location_geometries',
                'filter': ['any', ['==', ['geometry-type'], 'Polygon'], ['==', ['geometry-type'], 'MultiPolygon']],
                'layout': {},
                'paint': {
                    'fill-color': '#088',
                    'fill-opacity': 0.35,
                }
            });
        }
        if (!map.getLayer("location_polygon_outline")) {
            map.addLayer({
                'id': 'location_polygon_outline',
                'type': 'line',
                'source': 'location_geometries',
                'filter': ['any', ['==', ['geometry-type'], 'Polygon'], ['==', ['geometry-type'], 'MultiPolygon']],
                'paint': {
                    'line-width': 2,
                    'line-color': '#088',
                    'line-opacity': 0.8,
                }
            });
        }
        if (!map.getLayer("location_line_strings")) {
            map.addLayer({
                'id': 'location_line_strings',
                'type': 'line',
                'source': 'location_geometries',
                'filter': ['any', ['==', ['geometry-type'], 'LineString'], ['==', ['geometry-type'], 'MultiLineString']],
                'paint': {
                    'line-width': 4,
                    'line-color': '#088',
                    'line-opacity': 0.8,
                },
                'layout': {
                    'line-cap': 'round',
                    'line-join': 'round',
                }
            });
        }
        if (!map.getLayer("location_points")) {
            map.addLayer({
                'id': 'location_points',
                'type': 'circle',
                'source': 'location_geometries',
                'filter': ['any', ['==', ['geometry-type'], 'Point'], ['==', ['geometry-type'], 'MultiPoint']],
                'paint': {
                    'circle-stroke-width': 2,
                    'circle-stroke-color': '#FFF',
                    'circle-color': '#088',
                    'circle-opacity': 0.8,
                    'circle-radius': 7,
                },
            });
        }
        map.fitBounds(
            this.getFeatureBounds(geometry), {
                padding: 50,
                duration: 300
            }
        );
    }

    getFeatureBounds(polygons) {
        const turfBounds = turf.bbox(polygons);
        return turfBounds;
    }
}

const mapUtils = new MapUtils();