Vue.component("global-map", {
  props: {
    value: {
      default: [],
    },

    i18n: {},
    legend: {
      default: true,
    },
  },

  data: function () {
    return {
      locations: this.value.length ? this.value : [],
      mapHeight: 300,
      zoom: 10,
      mapKey: 0,
      markers: {},
      markersOnScreen: {},
      // Event routes
      eventLinks: null,
      mapsApiEndpoint: mapsApiEndpoint,
      subdomains: null,
      lat: geoMapDefaultCenter.lat,
      lng: geoMapDefaultCenter.lng,
      attribution:
        '&copy; <a target="_blank" href="http://osm.org/copyright">OpenStreetMap</a> contributors',
      osmAttribution:
        '&copy; <a target="_blank" href="http://osm.org/copyright">OpenStreetMap</a> contributors',
      satellite: null,
      defaultTile: true,
      measureControls: null,
      map: null,
      category: {
        location: {
          id: 'location',
          filter: ['==', ['get', 'markerType'], ['literal', 'location']],
          color: '#00a1f1',
          visible: true
        },
        geomarker: {
          id: 'geomarker',
          filter: ['==', ['get', 'markerType'], ['literal', 'geomarker']],
          color: '#ffbb00',
          visible: true
        },
        event: {
          id: 'event',
          filter: ['==', ['get', 'markerType'], ['literal', 'event']],
          color: '#00f166',
          visible: true
        }
      },
      allFeatures: [],
    };
  },

  mounted() {
    this.addLocationMarkerTypes();
    this.initMap();
  },

  watch: {
    value(val, old) {
      if ((val && val.length) || val !== old) {
        this.locations = val;
      }
    },

    locations() {
      this.addLocationMarkerTypes();

      if(this.map && this.map.isStyleLoaded()){
        this.addMarkers();
        this.fitMarkers();
      }

      this.$emit("input", this.locations);
    },
  },

  methods: {
    initMap() {
      let mlMapContainer = this.$refs.mapContainer
  
      let bounds = this.getLocationBounds();
      if(bounds) {
        this.lat = bounds.getCenter().lat;
        this.lng = bounds.getCenter().lng;
      }

      mapUtils.loadBaseLayer().then((style) => {
        this.map = new maplibregl.Map({
          container: mlMapContainer,
          style: style,
          center: [this.lng, this.lat],
          zoom: this.zoom,
          maxZoom: 18,
        });
    
        this.map.addControl(new maplibregl.NavigationControl());
    
        this.map.addControl(new maplibregl.FullscreenControl());
    
        this.map.addControl(new maplibreGLMeasures.default({
          lang: {
            areaMeasurementButtonTitle: 'Measure area',
            lengthMeasurementButtonTitle: 'Measure length',
            clearMeasurementsButtonTitle:  'Clear measurements',
          },
          units: 'imperial',
          style: {
            text: {
                radialOffset:  0.9,
                letterSpacing: 0.05,
                color: '#D20C0C',
                haloColor: '#fff',
                haloWidth: 0,
                font: 'Noto Sans Bold',
            },
            common: {
                midPointRadius: 5,
                midPointColor: '#D20C0C',
                midPointHaloRadius: 5,
                midPointHaloColor: '#FFF',
            },
            areaMeasurement: {
                fillColor: '#D20C0C',
                fillOutlineColor: '#D20C0C',
                fillOpacity: 0.01,
                lineWidth: 2,
            },
            lengthMeasurement: {
                lineWidth: 2,
                lineColor: "#D20C0C",
            },
          }
        }))
    
        this.map.once('render', () => {
          this.map.resize();
          this.fitMarkers(false); 
        });
        // see https://github.com/mapbox/mapbox-gl-js/issues/9779, https://github.com/mapbox/mapbox-gl-js/issues/8691
        this.map.once('idle', () => {
          this.addMarkers();
          this.fitMarkers(false);
        });
        this.map.on('render', () => {
          this.updateMarkers();
        });
    
        this.map.on('click', 'clusters', this.onClusterClick);
    
        this.map.on('click', 'unclustered-point', this.onUnclusteredClick);

        this.map.on('click', 'location_points', this.onUnclusteredClick);
        this.map.on('click', 'location_line_strings', this.onUnclusteredClick);
        this.map.on('click', 'location_polygon', this.onUnclusteredClick);
    
        this.map.on('resize', () => {
          this.fitMarkers();
        });
        
        this.map.on('styleimagemissing', (e) => {
          this.loadEventLinkArrowImage();
        });
      });
        // replace google sattelite maps with mapbox maps: https://docs.mapbox.com/mapbox-gl-js/example/satellite-map/
    },

    loadEventLinkArrowImage() {
      try {
        let img = document.createElement('img');
        img.src = "data:image/svg+xml;base64,PHN2ZyB0cmFuc2Zvcm09InJvdGF0ZSg5MCkiIHZpZXdCb3g9Ii0wLjIgLTAuMiA0LjQgNC40IiBoZWlnaHQ9IjEwIiB3aWR0aD0iMTAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0ibTIgMCAyIDJ2MkwyIDIgMCA0VjJ6Ii8+PC9zdmc+"
        this.map.addImage("arrow", img, { sdf: true });
      } catch(e) {}
    },

    toggleSatellite() {
      // use subdomains to identify state
      if (this.defaultTile) {
        this.defaultTile = false;
        this.satellite.addTo(this.$refs.map.mapObject);
      } else {
        this.defaultTile = true;
        this.$refs.map.mapObject.removeLayer(this.satellite);
      }

      // Working hack : redraw the tile layer component via Vue key
      this.mapKey += 1;
    },

    redraw() {
      this.map.resize();
    },

    async onClusterClick(e) {
      const el = e.currentTarget;
      const clusterId = el.getAttribute('cluster_id');
      const zoom = await this.map.getSource('markers').getClusterExpansionZoom(parseInt(clusterId));
      const coords = el.getAttribute('cluster_loc').split(',')
      const loc = new maplibregl.LngLat(coords[0],coords[1]);
      this.map.easeTo({
          center: loc,
          zoom
      });
    },

    async onUnclusteredClick(e) {
      const coordinates = turf.centerOfMass(turf.featureCollection(e.features)).geometry.coordinates;

      const loc = e.features[0].properties;

      // Ensure that if the map is zoomed out such that
      // multiple copies of the feature are visible, the
      // popup appears over the copy being pointed to.
      while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
      }

      new maplibregl.Popup()
          .setLngLat(e.lngLat)
          .setHTML(
            `<div>
              <span title="No." class="map-bid">${loc.number || ""}</span>
              <span title="Primary Record ID" class="map-bid">${loc.parentId || ""}</span>
              
              <div class="body-2 font-weight-bold">${loc.title || ""}</div>

              <div class="subtitle">
              ${loc.lat ? loc.lat.toFixed(6) + "," : ""} ${loc.lng ? loc.lng.toFixed(6) : ""}
              </div>

              <span class="mt-1 subtitle">${loc.full_string || ""}</span>
              <div>
              <span title="Main Investigation" class="map-bid">${loc.mainStr || ""}</span>
              <span title="Marker Type" class="map-bid">${loc.type || ""}</span>
              <span title="Event Type" class="map-bid">${loc.eventtype || ""}</span>
            </div>`
              
          )
          .addTo(this.map);
    },

    toggleVisibility(categoryId) {
      this.category[categoryId].visible = !this.category[categoryId].visible;
      this.addMarkers();
      this.fitMarkers();
    },

    addMarkers() {
      if (this.locations.length) {
        let eventLocations = [];
        let geometryLocations = [];
        this.allFeatures = [];

        for (loc of this.locations) {
          if(!this.category[loc.markerType].visible) {
            continue;
          }

          let event = { 
            "type": "Feature", 
            "properties": {
              "color": loc.color + 'A5',
              "fillColor": loc.color + '80',
              "number": loc.number || "",
              "parentId": loc.parentId || "",
              "title": loc.title || "",
              "full_string": loc.full_string || "",
              "mainStr": (loc.mainStr?loc.mainStr:""),
              "type": (loc.type?loc.type:""),
              "eventtype": (loc.eventtype?loc.eventtype:""),
              "markerType": loc.markerType
            }, 
            "geometry": loc.geometry
          }

          if(loc.geometry && loc.geometry.coordinates) {
            geometryLocations.push(event);
            if (loc.type === "Event") {  
              eventLocations.push(loc);
            }
          } 

          this.allFeatures.push(event);
        }

        if(geometryLocations.length) this.addGeometryLocations(geometryLocations);

        this.addEventRoutes(eventLocations);
      }
    },

    addGeometryLocations(features) {
      const featureCollection = turf.featureCollection(features);
      mapUtils.addGeometries(this.map, featureCollection);
    },

    updateMarkers() {
      const newMarkers = {};
      const features = this.map.querySourceFeatures('markers');
      
      // for every cluster on the screen, create an HTML marker for it (if we didn't yet),
      // and add it to the map if it's not there already
      for (const feature of features) {
          const coords = feature.geometry.coordinates;
          const props = feature.properties;
          if (!props.cluster) continue;
          const id = props.cluster_id;

          let marker = this.markers[id];
          if (!marker) {
              const el = this.createDonutChart(props);
              marker = this.markers[id] = new maplibregl.Marker({
                  element: el,
                  interactive: true
              })
              .setLngLat(coords);
              marker.getElement().addEventListener('click', this.onClusterClick);
              marker.getElement().setAttribute('cluster_id', id);
              marker.getElement().setAttribute('cluster_loc', coords);
          }
          newMarkers[id] = marker;

          if (!this.markersOnScreen[id]) marker.addTo(this.map);
      }
      // for every marker we've added previously, remove those that are no longer visible
      for (const id in this.markersOnScreen) {
          if (!newMarkers[id]) {
            this.markersOnScreen[id].remove();
          }
      }
      this.markersOnScreen = newMarkers;
    },

    createDonutChart(props) {
      const offsets = [];
      const categories = [
          {count: props.locations, color: this.category.location.color},
          {count: props.geomarkers, color: this.category.geomarker.color},
          {count: props.events, color: this.category.event.color},
      ];
      let total = 0;
      for (const category of categories) {
          offsets.push(total);
          total += category.count;
      }
      const fontSize =
          total >= 1000 ? 22 : total >= 100 ? 20 : total >= 10 ? 18 : 16;
      const r =
          total >= 1000 ? 50 : total >= 100 ? 32 : total >= 10 ? 24 : 18;
      const r0 = Math.round(r * 0.6);
      const w = r * 2;

      let html = `<div>
          <svg width="${w}" height="${w}" viewbox="0 0 ${w} ${w}" text-anchor="middle" style="font: ${fontSize}px sans-serif; display: block">`;

      for (let i = 0; i < categories.length; i++) {
          html += this.donutSegment(
              offsets[i] / total,
              (offsets[i] + categories[i].count) / total,
              r,
              r0,
              categories[i].color + 'A5'
          );
      }
      html += `<circle cx="${r}" cy="${r}" r="${r0}" fill="rgb(255, 255, 255, 0.8)" />
          <text dominant-baseline="central" transform="translate(${r}, ${r})">
              ${total.toLocaleString()}
          </text>
          </svg>
          </div>`;

      const el = document.createElement('div');
      el.innerHTML = html;
      return el.firstChild;
    },

    donutSegment(start, end, r, r0, color) {
        if (end - start === 1) end -= 0.00001;
        const a0 = 2 * Math.PI * (start - 0.25);
        const a1 = 2 * Math.PI * (end - 0.25);
        const x0 = Math.cos(a0),
            y0 = Math.sin(a0);
        const x1 = Math.cos(a1),
            y1 = Math.sin(a1);
        const largeArc = end - start > 0.5 ? 1 : 0;

        // draw an SVG path
        return `<path d="M ${r + r0 * x0} ${r + r0 * y0} L ${r + r * x0} ${
            r + r * y0
        } A ${r} ${r} 0 ${largeArc} 1 ${r + r * x1} ${r + r * y1} L ${
            r + r0 * x1
        } ${r + r0 * y1} A ${r0} ${r0} 0 ${largeArc} 0 ${r + r0 * x0} ${
            r + r0 * y0
        }" fill="${color}" />`;
    },

    hasMarkers() {
      return this.locations.length > 0;
    },

    addLocationMarkerTypes(){
      for (loc of this.locations) {
        if(loc.color == this.category.location.color) {
          loc.markerType = this.category.location.id;
        } else if(loc.color == this.category.geomarker.color) {
          loc.markerType = this.category.geomarker.id;
        } else if(loc.color == this.category.event.color) {
          loc.markerType = this.category.event.id;
        } else {
          continue;
        }
      } 
    },

    hasLocations() {
      return this.hasMarkers() && this.locations.some((location) => {return location.markerType == this.category.location.id });
    },

    hasGeomarkers() {
      return this.hasMarkers() && this.locations.some((location) => {return location.markerType == this.category.geomarker.id });
    },

    hasEvents() {
      return this.hasMarkers() && this.locations.some((location) => {return location.markerType == this.category.event.id });
    },

    getLocationBounds() {
      if (this.locations.length) {
        try {
          var coordinates = this.locations;

          var bounds = coordinates.reduce(function(bounds, coord) {
            return bounds.extend(coord);
          }, new maplibregl.LngLatBounds(coordinates[0], coordinates[0]));

          return bounds;
        } catch(e) {}
      }
      return null;
    },

    fitMarkers(animate = true) {
      let locations = this.allFeatures.filter((feature) => {return (feature.geometry && feature.geometry.coordinates)});
      if(locations.length) {
        const featureCollection = turf.featureCollection(locations);
        this.map.fitBounds(
          mapUtils.getFeatureBounds(featureCollection), {
            padding: 50,
            duration: 600
          }
        );
      }
    },

    getBSplineCurve(eventLocations) {
      var data = [];
      for (let i = 0; i < eventLocations.length - 1; i++) {
        if (eventLocations[i].zombie || eventLocations[i + 1].zombie) continue;
        // get start and end point at the center of mass of each feature
        let start = turf.centerOfMass(eventLocations[i].geometry);
        let end = turf.centerOfMass(eventLocations[i + 1].geometry);
        // extra logic to attempt to get start and end points that are touching the feature
        if ((eventLocations[i].geometry.type.includes("Polygon") || eventLocations[i].geometry.type.includes("LineString")) && !turf.booleanTouches(start, eventLocations[i].geometry)) {
          start = turf.pointOnFeature(eventLocations[i].geometry);
        }
        if (eventLocations[i].geometry.type == "MultiPoint") {
          start = turf.point(eventLocations[i].geometry.coordinates[0]);
        }
        if ((eventLocations[i + 1].geometry.type.includes("Polygon") || eventLocations[i + 1].geometry.type.includes("LineString")) && !turf.booleanTouches(end, eventLocations[i + 1].geometry)) {
          end = turf.pointOnFeature(eventLocations[i + 1].geometry);
        }
        if (eventLocations[i + 1].geometry.type == "MultiPoint") {
          start = turf.point(eventLocations[i + 1].geometry.coordinates[0]);
        }
        // get the points for the bspline curve that connects the start and end points
        const distance = turf.distance(start, end, { units: 'miles' });
        const bearing = turf.bearing(start, end);
        const midpoint = turf.midpoint(start, end);
        const leftSideArc = bearing + 90 > 180 ? -180 + (bearing + 90 - 180) : bearing + 90;
        const destination = turf.destination(midpoint, distance / 5, leftSideArc, { units: 'miles' });
        const curvedLine = turf.bezierSpline(
          turf.lineString([start.geometry.coordinates, destination.geometry.coordinates, end.geometry.coordinates]),
          {sharpness:1.0}
        );
        
        data.push(curvedLine);
      }
      return turf.featureCollection(data);
    },
    
    addEventRoutes(eventLocations) {
      if (this.map.getSource('event-route')) { 
        this.map.removeLayer('event-routes');
        this.map.removeLayer('event-arrows');
        this.map.removeSource('event-route');
      }

      if (eventLocations.length == 0) return;

      this.map.addSource('event-route', {
        "type": "geojson",
        "data": this.getBSplineCurve(eventLocations)
      });
      this.map.addLayer({
        "id": "event-routes",
        "source": "event-route",
        "type": "line",
        "paint": {
          "line-width": 5,
          "line-color": "#00f166",
          "line-opacity": 0.4,
        }
      });
      this.map.addLayer({
        "id": "event-arrows",
        "type": "symbol",
        "source": "event-route",
        "layout": {
          "symbol-placement": "line",
          "symbol-spacing": 20,
          "icon-allow-overlap": true,
          "icon-image": "arrow",
          "icon-size": 1.0,
          "visibility": "visible"
        },
        "paint": {
          "icon-color": "#00ff66",
        },
        minzoom: 4,
      });
    },
  },

  template: `
      <div>
      <v-card outlined color="grey lighten-3">
        <v-card-text>
          <div v-if="legend && hasMarkers()" class="map-legend d-flex mb-3 align-center" style="column-gap: 10px">
            <div class="caption" v-if="hasLocations()">
              <v-icon @click="toggleVisibility('location')" small :color="category.location.visible?category.location.color:'#cccccc'"> mdi-checkbox-blank-circle</v-icon>
              {{ i18n.locations_ }}
            </div>
            <div class="caption" v-if="hasGeomarkers()">
              <v-icon @click="toggleVisibility('geomarker')" small :color="category.geomarker.visible?category.geomarker.color:'#cccccc'"> mdi-checkbox-blank-circle</v-icon>
              {{ i18n.geoMarkers_ }}
            </div>
            <div class="caption" v-if="hasEvents()">
              <v-icon @click="toggleVisibility('event')" small :color="category.event.visible?category.event.color:'#cccccc'"> mdi-checkbox-blank-circle</v-icon>
              {{ i18n.events_ }}
            </div>

          </div>

          <l-map id="mlMapContainer" ref="mapContainer" :style="'position: relative; display: inline-block; height: '+ mapHeight + 'px; width: 100%;; resize: vertical'"></l-map>

        </v-card-text>
      </v-card>
      </div>
    `,
});
