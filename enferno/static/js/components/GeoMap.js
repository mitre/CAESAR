// const maplibreGl = require("../maplibre-gl");

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
      default: true,
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
  },

  computed: {
    // map() {
    //    //return this.$refs.map.mapObject;
    //   //  return this.$refs.mapContainer.map;
    //    return this.map;
    // },

    mapCenter() {
      if (this.lat && this.lng) {
        return {lat: this.lat, lng: this.lng};
      }
      return geoMapDefaultCenter;
    },

    extra() {
      // computed property to display other markers, it should exclude the main marker
      if (this.others && this.value) {
        // console.log(this.others.filter(x=> x.lat!=this.value.lat && x.lng != this.value.lng));
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

      location: null,
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
    value(val) {
      if (!val) {
        this.lat = undefined;
        this.lng = undefined;
        this.radius = 100; // reset
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
      }
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
  },

  unmounted() {
    mlMap.value?.remove();
  },

  mounted() {
    window.addEventListener("resize", this.fixMap);

    this.fixMap();
    this.broadcast();

    let mlMapContainer = this.$refs.mapContainer
    let mlMap = {};
    mlMap.value = new maplibregl.Map({
      container: mlMapContainer,
      style: `https://tileserver.apps.epic-osc.mitre.org/styles/bright/style.json`,
      center: [this.mapCenter.lng, this.mapCenter.lat],
      zoom: this.mapZoom,
    });
    
    this.map = mlMap.value;

    this.map.addControl(new maplibregl.NavigationControl());
    this.map.addControl(new maplibregl.FullscreenControl());
    this.map.on('click', (e) => {this.updateMarker(e)});

    if (this.value) {
      this.$nextTick(() => {this.updateMarker()});
    }

    if (this.others) {
      this.others.filter(
        (x) => !this.value || (x.lat != this.value.lat && x.lng != this.value.lng),
      ).forEach((marker)=>{
        new maplibregl.Marker({color: "#DDDDDD"})
          .setLngLat([marker.lng, marker.lat])
          .addTo(this.map);
      });
    }

    // create a DOM element for the marker
    // const el = document.createElement('div');
    // el.className = 'marker';
    // el.style.background = 'red';
    // el.style.width = `50px`;
    // el.style.height = `50px`;
    // el.style.borborderRadius = `25px`;

    // // add marker to map
    // new maplibregl.Marker({element: el})
    //   .setLngLat([this.mapCenter.lng, this.mapCenter.lat])
    //   .addTo(mlMap.value);

   
    // this.satellite = L.gridLayer.googleMutant({
    //   type: "satellite", // valid values are 'roadmap', 'satellite', 'terrain' and 'hybrid'
    // });
  },

  // clean up resize event listener
  beforeDestroy() {
    window.removeEventListener("resize", this.fixMap);
  },

  methods: {
    fixMap() {
      this.$nextTick(() => {
        if (this.map) {
          this.map.resize();
        }

        // Add error handling for the tile layer
        // L.tileLayer(this.mapsApiEndpoint)
        //   .on("error", function (error) {
        //     console.error("Tile layer error:", error);
        //   })
        //   .addTo(this.map);
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

    updateMarker(evt) {
      let loc = [this.mapCenter.lng, this.mapCenter.lat];
      if (evt && evt.lngLat) {
        loc = [evt.lngLat.lng, evt.lngLat.lat];
      } else if (this.lat && this.lng) {
        loc = [this.lng, this.lat];
      }

      if(!this.marker) {
        this.marker = new maplibregl.Marker({
          id: 'editing-geolocation',
          draggable: true
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

      if (this.editMode) {
        // this.map.flyTo({
        //   center: loc
        // });
        this.lat = loc[1];
        this.lng = loc[0];
      }
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
      // Only return obj if both lat,lng values present
      if (this.lat && this.lng) {
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
              <v-text-field dense type="number" min="-90" max="90" v-model.number="lat">
                <template #label>
                    {{ translations.latitude_ }} <span class="red--text" v-if="required"><strong>* </strong></span>
                </template>
              </v-text-field>
              <v-text-field dense type="number" min="-180" max="180" :label="translations.longitude_" v-model.number="lng">
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
                  :max="100000"
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
