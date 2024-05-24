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
      // Marker cluster
      // markerGroup: null,
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
      arrow: '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="-1 -1 22 22"><g><path d="m 10,0 10,10 0,10 -10,-10 -10,10 0,-10 z"/></g></svg>'
    };
  },

  mounted() {
    let mlMapContainer = this.$refs.mapContainer

    this.map = new maplibregl.Map({
      container: mlMapContainer,
      style: `https://tileserver.apps.epic-osc.mitre.org/styles/bright/style.json`,
      center: [this.lng, this.lat],
      zoom: this.zoom,
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
            font: 'Klokantech Noto Sans Bold',
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

    this.map.once('load', async () => {
      this.map.resize();
    });

    this.map.on('render', this.init);

    this.map.on('click', 'clusters', this.onClusterClick);

    this.map.on('click', 'unclustered-point', this.onUnclusteredClick);
    
    this.map.on('render', () => {
      this.updateMarkers();
    });
    
    this.map.on('styleimagemissing', (e) => {
      let img = document.createElement('img');
      img.src = "data:image/svg+xml;base64,PHN2ZyB0cmFuc2Zvcm09InJvdGF0ZSg5MCkiIHZpZXdCb3g9Ii0wLjIgLTAuMiA0LjQgNC40IiBoZWlnaHQ9IjEwIiB3aWR0aD0iMTAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0ibTIgMCAyIDJ2MkwyIDIgMCA0VjJ6Ii8+PC9zdmc+"
      this.map.addImage("arrow", img, { sdf: true });
    });

    // replace google sattelite maps with mapbox maps: https://docs.mapbox.com/mapbox-gl-js/example/satellite-map/
  },

  watch: {
    value(val, old) {
      if ((val && val.length) || val !== old) {
        this.locations = val;
        //this.fitMarkers();
        this.addMarkers();
      }
      if (val.length === 0) {
        this.$refs.map.mapObject.setView([this.lat, this.lng]);
      }
    },

    locations() {
      this.$emit("input", this.locations);
    },
  },

  methods: {

    init() {
      if (this.map.isStyleLoaded()) {
        this.map.off('render', this.init);
        this.addMarkers();
      }
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

    fsHandler() {
      // TODO: this callback doesn't exist in the maplibre fullscreen impl
      // allow some time for the map to enter/exit fullscreen
      setTimeout(() => this.addMarkers(), 500);
    },

    redraw() {
      // this.$refs.map.mapObject.invalidateSize();
      this.map.resize();
    },

    async onClusterClick(e) {
      // const features = this.map.queryRenderedFeatures(e.point);
      // const clusterId = features[0].properties.cluster_id;
      const el = e.currentTarget;
      const clusterId = el.getAttribute('cluster_id');
      const zoom = await this.map.getSource('markers').getClusterExpansionZoom(parseInt(clusterId));
      const coords = el.getAttribute('cluster_loc').split(',')
      const loc = new maplibregl.LngLat(coords[0],coords[1]);
      this.map.easeTo({
          // center: features[0].geometry.coordinates,
          center: loc,
          zoom
      });
    },

    async onUnclusteredClick(e) {
      const coordinates = e.features[0].geometry.coordinates.slice();

      const loc = e.features[0].properties;

      // Ensure that if the map is zoomed out such that
      // multiple copies of the feature are visible, the
      // popup appears over the copy being pointed to.
      while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
      }

      new maplibregl.Popup()
          .setLngLat(coordinates)
          .setHTML(
            `<div>
              <span title="No." class="map-bid">${loc.number || ""}</span>
              <span title="Bulletin ID" class="map-bid">${loc.parentId || ""}</span>
              
              <div class="body-2 font-weight-bold">${loc.title || ""}</div>

              <div class="subtitle">
              ${loc.lat.toFixed(6)}, ${loc.lng.toFixed(6)}
              </div>

              <span class="mt-1 subtitle">${loc.full_string || ""}</span>
              <div>
              <span title="Main Incident" class="map-bid">${loc.mainStr || ""}</span>
              <span title="Marker Type" class="map-bid">${loc.type || ""}</span>
              <span title="Event Type" class="map-bid">${loc.eventtype || ""}</span>
            </div>`
              
          )
          .addTo(this.map);
    },

    toggleVisibility(categoryId) {
      this.category[categoryId].visible = !this.category[categoryId].visible;
      this.addMarkers();
    },

    addMarkers() {
      if (!this.map.isStyleLoaded()) return; 

      if (this.map.getSource('markers')) {
        this.map.removeLayer('unclustered-point');
        this.map.removeSource('markers');
      }

      if (this.locations.length) {
        let allLocations = [];
        let eventLocations = [];
        
        for (loc of this.locations) {
          
          if(loc.color == this.category.location.color && this.category.location.visible) {
            loc.markerType = this.category.location.id;
          } else if(loc.color == this.category.geomarker.color && this.category.geomarker.visible) {
            loc.markerType = this.category.geomarker.id;
          } else if(loc.color == this.category.event.color && this.category.event.visible) {
            loc.markerType = this.category.event.id;
          } else {
            continue;
          }

          let event = { 
            "type": "Feature", 
            "properties": {
              "color": loc.color + 'A5',
              "number": loc.number || "",
              "parentId": loc.parentId || "",
              "title": loc.title || "",
              "lat": loc.lat,
              "lng": loc.lng,
              "full_string": loc.full_string || "",
              "mainStr": (loc.mainStr?loc.mainStr:""),
              "type": (loc.type?loc.type:""),
              "eventtype": (loc.eventtype?loc.eventtype:""),
              "markerType": loc.markerType
            }, 
            "geometry": { 
              "type": "Point", 
              "coordinates": [ loc.lng, loc.lat, 0.0 ] 
            } 
          }
          allLocations.push(event);

          if (loc.type === "Event") {  
            eventLocations.push(loc);
          }
        }

        this.addEventRoutes(eventLocations);

        this.map.addSource('markers', {
          type: 'geojson',
          data: {
            "type": "FeatureCollection",
            "features": allLocations
          },
          cluster: true,
          clusterMaxZoom: 16, // Max zoom to cluster points on
          clusterRadius: 15, // Radius of each cluster when clustering points (defaults to 30)
          clusterProperties: {
            // keep separate counts for each category in a cluster
            'locations': ['+', ['case', this.category.location.filter, 1, 0]],
            'geomarkers': ['+', ['case', this.category.geomarker.filter, 1, 0]],
            'events': ['+', ['case', this.category.event.filter, 1, 0]],
          }
        });

        this.map.addLayer({
            id: 'unclustered-point',
            type: 'circle',
            source: 'markers',
            filter: ['!', ['has', 'point_count']],
            paint: {
                'circle-color': ["get", "color"],
                //'circle-opacity': 0.65, // this seems to have no effect on opacity.
                'circle-radius': 8,
                'circle-stroke-width': 1,
                'circle-stroke-color': '#fff'
            }
        });
      }
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
          if (!newMarkers[id]) this.markersOnScreen[id].remove();
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

    // TODO: remove this old leaflet method. 
    //   remaining items...
    //   - measuring tool
    //   - fit markers 
    fitMarkers() {
      // construct a list of markers to build a feature group

      // const map = this.$refs.map.mapObject;

      // if (this.markerGroup) {
      //   map.removeLayer(this.markerGroup);
      // }

      // this.markerGroup = L.markerClusterGroup({
      //   maxClusterRadius: 20,
      // });

      if (this.locations.length) {
        let eventLocations = [];

        // Add event linestring links if any available
        if (eventLocations.length > 1) {
          // this.addEventRouteLinks(eventLocations);
          this.addEventRoutes(eventLocations);
        }

        if (!this.measureControls) {
          this.measureControls = L.control.polylineMeasure({
            position: "topleft",
            unit: "kilometres",
            fixedLine: {
              // Styling for the solid line
              color: "rgba(67,157,146,0.77)", // Solid line color
              weight: 2, // Solid line weight
            },

            arrow: {
              // Styling of the midway arrow
              color: "rgba(67,157,146,0.77)", // Color of the arrow
            },
            showBearings: false,
            clearMeasurementsOnStop: false,
            showClearControl: true,
            showUnitControl: true,
          });

          // this.measureControls.addTo(map);
        }

        // Fit map of bounds of clusterLayer
        // let bounds = this.markerGroup.getBounds();
        // this.markerGroup.addTo(map);
        // map.fitBounds(bounds, { padding: [20, 20] });

        if (map.getZoom() > 14) {
        //   // flyout of center when map is zoomed in too much (single marker or many dense markers)
          map.flyTo(map.getCenter(), 10, { duration: 1 });
        }
      }

      map.invalidateSize();
    },

    getBSplineCurve(eventLocations) {
      var data = [];
      for (let i = 0; i < eventLocations.length - 1; i++) {
        if (eventLocations[i].zombie || eventLocations[i + 1].zombie) continue;
        const startCoord = [eventLocations[i].lng, eventLocations[i].lat];
        const endCoord = [eventLocations[i + 1].lng, eventLocations[i + 1].lat];
        var start = turf.point(startCoord);
        var end = turf.point(endCoord);

        const distance = turf.distance(start, end, { units: 'miles' });
        const bearing = turf.bearing(start, end);
        const midpoint = turf.midpoint(start, end);
        const leftSideArc = bearing + 90 > 180 ? -180 + (bearing + 90 - 180) : bearing + 90;
        const destination = turf.destination(midpoint, distance / 5, leftSideArc, { units: 'miles' });
        const curvedLine = turf.bezierSpline(
          turf.lineString([startCoord, destination.geometry.coordinates, endCoord]),
          {sharpness:1.0}
        );
        
        data.push(curvedLine);
      }
      return turf.featureCollection(data);
    },
    
    addEventRoutes(eventLocations) {

      // https://stackoverflow.com/questions/68021824/give-curved-line-a-deeper-arc-in-turf-js-and-mapbox

      if (this.map.getSource('route')) {
        this.map.removeLayer('routes');
        this.map.removeLayer('arrows');
        this.map.removeSource('route');
      }

      if (eventLocations.length == 0) return;
         
      this.map.addSource('route', {
        "type": "geojson",
        "data": this.getBSplineCurve(eventLocations)
      });
      this.map.addLayer({
        "id": "routes",
        "source": "route",
        "type": "line",
        "paint": {
          "line-width": 7,
          "line-color": "#00f166",
          "line-opacity": 0.2,
        }
      });
      this.map.addLayer({
        "id": "arrows",
        "type": "symbol",
        "source": "route",
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
        minzoom: 8,
      });

      // potential method for animating feature layer: https://docs.mapbox.com/mapbox-gl-js/example/animate-ant-path/
    },

    addEventRouteLinks(eventLocations) {
      const map = this.$refs.map.mapObject;

      // Remove existing eventRoute linestrings
      if (this.eventLinks) {
        map.removeLayer(this.eventLinks);
      }
      this.eventLinks = L.layerGroup({}).addTo(map);

      for (let i = 0; i < eventLocations.length - 1; i++) {
        const startCoord = [eventLocations[i].lat, eventLocations[i].lng];
        const endCoord = [eventLocations[i + 1].lat, eventLocations[i + 1].lng];

        // If the next eventLocation has the zombie attribute, do not draw the curve
        if (eventLocations[i + 1].zombie) {
          // Add a circle marker for the zombie event location
          L.circleMarker(endCoord, {
            radius: 5,
            fillColor: "#ff7800",
            color: "#000",
            weight: 1,
            opacity: 1,
            fillOpacity: 0.8,
          }).addTo(this.eventLinks);
          continue; // Skip to the next iteration
        }

        // const midpointCoord = this.getCurveMidpointFromCoords(
        //   startCoord,
        //   endCoord,
        // );

        // // Create bezier curve path between events
        // const curve = L.curve(["M", startCoord, "Q", midpointCoord, endCoord], {
        //   color: "#00f166",
        //   weight: 4,
        //   opacity: 0.4,
        //   dashArray: "5",
        //   animate: { duration: 15000, iterations: Infinity },
        // }).addTo(this.eventLinks);

        // const curveMidPoints = curve.trace([0.8]);
        // const arrowIcon = L.icon({
        //   iconUrl: "/static/img/direction-arrow.svg",
        //   iconSize: [12, 12],
        //   iconAnchor: [6, 6],
        // });

        // curveMidPoints.forEach((point) => {
        //   const rotationAngle = this.getVectorDegrees(startCoord, endCoord);
        //   L.marker(point, {
        //     icon: arrowIcon,
        //     rotationAngle: rotationAngle,
        //   }).addTo(this.eventLinks);
        // });
      }
    },
  },

  template: `
      <div>
      <v-card outlined color="grey lighten-3">
        <v-card-text>
          <div v-if="legend" class="map-legend d-flex mb-3 align-center" style="column-gap: 10px">
            <div class="caption">
              <v-icon @click="toggleVisibility('location')" small :color="category.location.visible?category.location.color:'#cccccc'"> mdi-checkbox-blank-circle</v-icon>
              {{ i18n.locations_ }}
            </div>
            <div class="caption">
              <v-icon @click="toggleVisibility('geomarker')" small :color="category.geomarker.visible?category.geomarker.color:'#cccccc'"> mdi-checkbox-blank-circle</v-icon>
              {{ i18n.geoMarkers_ }}
            </div>
            <div class="caption">
              <v-icon @click="toggleVisibility('event')" small :color="category.event.visible?category.event.color:'#cccccc'"> mdi-checkbox-blank-circle</v-icon>
              {{ i18n.events_ }}
            </div>

          </div>

          <!--l-map @fullscreenchange="fsHandler" @dragend="redraw" ref="map" @ready="fitMarkers" :zoom="zoom"
                 :max-zoom="18"
                 :style=" 'resize:vertical;height:'+ mapHeight + 'px'"
                 :center="[lat,lng]" :options="{scrollWheelZoom:false}">
            <l-tile-layer v-if="defaultTile" :attribution="attribution" :key="mapKey" :url="mapsApiEndpoint"
                          :subdomains="subdomains">
            </l-tile-layer>
            <l-control class="example-custom-control">
              <v-btn v-if="__GOOGLE_MAPS_API_KEY__" @click="toggleSatellite" small fab>
                <img src="/static/img/satellite-icon.png" width="18"></img>
              </v-btn>
            </l-control>
          </l-map-->

          <l-map id="mlMapContainer" @ready="addMarkers" ref="mapContainer" :style="'position: relative; display: inline-block; height: '+ mapHeight + 'px; width: 100%;; resize: vertical'"></l-map>

        </v-card-text>
      </v-card>
      </div>
    `,
});
