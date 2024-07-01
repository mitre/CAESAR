
Vue.component("geo-map", {
  props: {
    title: String,
    value: {},

    mapHeight: {
      default: 300,
    },
    mapZoom: {
      default: 10,
    },
    editMode: {
      type: Boolean,
    },
    radiusControls: {
      type: Boolean,
      default: false,
    },
    others: [],
    required: {
      type: Boolean,
      default: false,
    },
    location: {}
  },

  computed: {

    mapCenter() {
      if (this.lat !== undefined && this.lng !== undefined) {
        return {lat: this.lat, lng: this.lng};
      }
      return geoMapDefaultCenter;
    },

    extra() {
      // computed property to display other markers, it should exclude the main marker
      if (this.others && this.value) {
        return this.others.filter(
          (x) => x.lat != this.value.lat && x.lng != this.value.lng,
        )
      }
      return [];
    },
  },

  data: function () {
    return {
      mapKey: 0,
      lat: this.value && this.value.lat,
      lng: this.value && this.value.lng,
      radius: this.value && this.value.radius ? this.value.radius : 1000, // Default to 1000

      subdomains: null,
      mapsApiEndpoint: mapsApiEndpoint,

      geometry: (this.value && this.value.geometry) || (this.location && this.location.geometry),
      attribution:
        '&copy; <a target="_blank" href="http://osm.org/copyright">OpenStreetMap</a> contributors',
      osmAttribution:
        '&copy; <a target="_blank" href="http://osm.org/copyright">OpenStreetMap</a> contributors',

      defaultTile: true,
      satellite: null,

      radiusCircle: null,      
    };
  },

  watch: {
    value(val, old) {
      if (!val) {
        this.lat = undefined;
        this.lng = undefined;
        this.radius = 100; // reset
        this.geometry = undefined;
        // this.location = undefined;
        return;
      }
      // Prevent string or negative radius on backend
      if (typeof val.radius !== "string" && val.radius >= 0) {
        this.radius = val.radius;
        this.clearAddRadiusCircle();
      }

      // Only send coordinate pairs to backend
      if (val.lat && val.lng) {
        this.lat = val.lat;
        this.lng = val.lng;
        if(val.geometry) this.geometry = val.geometry;
        // this.location = val;
        if(this.map && this.map.isStyleLoaded()) {
          // I have yet to see this statement reached
          this.updateLocations(true);
        }
      }
    },

    location(val, old) {
      if(this.location && this.location.geometry) this.geometry = location.geometry;
    },

    lat: {
      handler: "broadcast",
    },

    lng: {
      handler: "broadcast",
    },

    radius: {
      handler: "broadcast",
    },

    geometry: {
      handler: "broadcast",
    },
  },

  mounted() {
    this.initMap();
  },

  // clean up resize event listener
  beforeDestroy() {
    // this.geometry = undefined;
    // console.log("before destroy");
    // window.removeEventListener("resize", this.fixMap);
    // this.map?.remove();
  },

  methods: {
    initMap() {
      window.addEventListener("resize", this.fixMap);
  
      this.fixMap();

      mapUtils.loadBaseLayer().then((style) => {

        this.map = new maplibregl.Map({
          container: this.$refs.mapContainer,
          style: style,
          center: [this.mapCenter.lng, this.mapCenter.lat],
          zoom: this.mapZoom,
          maxZoom: 18
        });

        this.map.addControl(new maplibregl.NavigationControl());
        this.map.addControl(new maplibregl.FullscreenControl());
        if(this.editMode) this.map.on('click', (e) => {this.updateLocationsFromEvent(e)});

        this.map.once('idle', () => {
          // this.clearAll();
          this.updateLocations(true);
          if (this.others) {
            this.others.filter(
              (x) => !this.value || (x.lat != this.value.lat && x.lng != this.value.lng),
            ).forEach((marker)=>{
              new maplibregl.Marker({color: "#DDDDDD"})
                .setLngLat([marker.lng, marker.lat])
                .addTo(this.map);
            });
          }
        });
      });
    },

    clearAllLocations() {
      if(this.marker) {
        this.marker.remove();
        this.marker = null;
      }
      if (this.map.getSource('location_polygon')) {
        this.map.removeLayer('location_polygon');
        this.map.removeSource('location_polygon');
      }
    },

    fixMap() {
      this.$nextTick(() => {
        if (this.map) {
          this.map.resize();
        }
      });
    },

    toggleSatellite() {
      if (this.defaultTile) {
        this.satellite.addTo(this.map);
        this.defaultTile = false;
      } else {
        this.defaultTile = true;
        this.map.removeLayer(this.satellite);
      }

      // Working hack : redraw the tile layer component via Vue key
      this.mapKey += 1;
    },

    clearMarker(evt) {
      this.lat = this.lng = null;
      if(this.marker) {
        this.marker.remove();
        this.marker = null;
      }
      if (this.map.getSource('radius')) {
        this.map.removeLayer('circle-line');
        this.map.removeLayer('circle-fill');
        this.map.removeSource('radius');
      }
    },

    updateLocationsFromEvent(mapEvent, forceRefresh=false) {
      if (mapEvent && mapEvent.lngLat) {
        this.addLocations(mapEvent.lngLat, forceRefresh);
      }
    },

    updateLocations(forceRefresh=false) {
      this.addLocations(null, forceRefresh);
    },

    addLocations(eventLocation, forceRefresh=false) {
      let loc = [this.mapCenter.lng, this.mapCenter.lat];
      if (eventLocation) {
        loc = [eventLocation.lng, eventLocation.lat];
      } else if (this.lat !== undefined && this.lng !== undefined && !isNaN(parseFloat(this.lat)) && !isNaN(parseFloat(this.lng))) {
        loc = [this.lng, this.lat];
      }

      // if(forceRefresh) this.clearAllLocations();
      
      //this.clearAllLocations();

      if(this.geometry && this.geometry.type == "Point") {
        this.addMarker(loc);
      } else if(this.geometry && this.geometry.type == "MultiPolygon") {
        this.addPolygon(loc);
      } else if(loc && this.editMode) {
        this.addMarker(loc);
      }

      if (this.editMode) {
        this.lat = loc[1];
        this.lng = loc[0];
      }
    },
    
    addMarker(loc) {
      if(!this.marker) {
        this.marker = new maplibregl.Marker({
          id: 'editing-geolocation',
          draggable: this.editMode
        })
        .setLngLat(loc)
        .on('dragend', (evt) => {
          const lngLat = evt.target._lngLat;
          if (this.editMode) {
            this.lat = lngLat.lat;
            this.lng = lngLat.lng;
            this.map.flyTo({
              center: [this.lng, this.lat]
            });
          }
        })
        .addTo(this.map);
      } else {
        this.marker.setLngLat(loc);
      }
    },

    addPolygon(loc) {
      if(!this.map.getSource("location_polygon")) {  
        this.map.addSource('location_polygon', {
          'type': 'geojson',
          'data': {
              'type': 'Feature',
              'geometry': this.geometry
          }
        });
      }
      if(!this.map.getLayer("location_polygon")) {
        this.map.addLayer({
          'id': 'location_polygon',
          'type': 'fill',
          'source': 'location_polygon',
          'layout': {},
          'paint': {
              'fill-color': '#088',
              'fill-opacity': 0.5
          }
        });
      }
      this.map.fitBounds(
        mapUtils.getFeatureBounds(this.geometry), {
          padding: 10,
          duration: 600
        }
      );
    },

    clearAddRadiusCircle() {
      if (!this.radiusControls) {
        return;
      }

      // Remove existing radius circle if it exists
      if (this.map.getSource('radius')) {
        this.map.removeLayer('circle-line');
        this.map.removeLayer('circle-fill');
        this.map.removeSource('radius');
      }

      // If radius is not provided, return
      if (!this.radius) {
        return;
      }

      if (!this.lat || !this.lng) {
        return;
      }
      
      var center = [this.lng, this.lat];
      var options = { steps: 90, units: "meters", properties: { foo: "bar" } };
      var circle = turf.circle(center, this.radius, options);
      this.map.addSource('radius', {
        'type': 'geojson',
        'data': circle
      });
      this.map.addLayer({
        'id': 'circle-fill',
        'type': 'fill',
        'source': 'radius',
        'paint': {
          "fill-color": "rgb(51, 136, 255)",
          "fill-opacity": 0.2
        }
      });
      this.map.addLayer({
        'id': 'circle-line',
        'type': 'line',
        'source': 'radius',
        'paint': {
          "line-color": "rgb(51, 136, 255)",
          "line-opacity": 1.0,
          "line-width": 3
        }
      });

      debounce(() => {
        const bbox = turf.bbox(circle);
        this.map.fitBounds(bbox, {padding: 20, duration: 100});
      }, 250)();
    },

    broadcast() {
      if(!this.editMode) return;
      // Only return obj if both lat,lng values present
      if (this.lat !== undefined && this.lng !== undefined && !isNaN(parseFloat(this.lat)) && !isNaN(parseFloat(this.lng))) {
        const obj = { lat: this.lat, lng: this.lng };
        if (this.radiusControls && this.radius) {
          obj.radius = this.radius;
        }
        this.$emit("input", obj);
        return;
      }

      this.$emit("input", undefined);
    },
  },
  template: `
        <v-card class="pa-1" elevation="0">

          <v-card-text>
            <h3 v-if="title" class=" mb-5">{{ title }}</h3>
            <div v-if="editMode" class="d-flex" style="column-gap: 20px;">
              <v-text-field dense type="number" min="-90" max="90" v-model.number="lat" @keyup="updateLocations">
                <template #label>
                    {{ translations.latitude_ }} <span class="red--text" v-if="required"><strong>* </strong></span>
                </template>
              </v-text-field>
              <v-text-field dense type="number" min="-180" max="180" :label="translations.longitude_" v-model.number="lng" @keyup="updateLocations">
                <template #label>
                    {{ translations.longitude_ }} <span class="red--text" v-if="required"><strong>* </strong></span>
                </template>            
              </v-text-field>
              <v-btn v-if="lat&&lng" small @click="clearMarker" text fab>
                <v-icon>mdi-close</v-icon>
              </v-btn>
            </div>

            <div v-if="editMode && radiusControls">
              <v-slider
                  v-if="editMode && radiusControls"
                  class="mt-1 align-center"
                  :min="100"
                  :max="1000000"
                  :step="100"
                  thumb-label
                  track-color="gray lighten-2"
                  v-model.number="radius"
                  :label="translations.radius_"
              >
                <template v-slot:append>  
                    <v-text-field 
                        readonly
                        style="max-width:200px" 
                        v-model.number="radius"
                        :suffix="translations.meters_" 
                        outlined 
                        dense 
                    >
                    </v-text-field>
                </template>
              </v-slider>
            </div>

            <l-map id="mlMapContainer" ref="mapContainer" :style="'position: relative; display: inline-block; height: '+ mapHeight + 'px; width: 100%; resize: vertical'"></l-map>

          </v-card-text>

        </v-card>
        `,
});
