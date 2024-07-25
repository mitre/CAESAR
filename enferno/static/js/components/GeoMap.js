Vue.component("geo-map", {
  props: {
    title: String,

    mapHeight: {
      default: 300,
    },
    mapZoom: {
      default: 10,
    },
    editMode: {
      type: Boolean,
    },
    searchMode: {
      type: Boolean,
    },
    others: [],
    required: {
      type: Boolean,
      default: false,
    },
    value: {},
    isGeoJson: {
      type: Boolean,
    },
    pointEditMode: {
      type: Boolean,
    },
  },

  computed: {
    mapCenter() {
      if (this.lat !== undefined && this.lng !== undefined) {
        return { lat: this.lat, lng: this.lng };
      }
      return geoMapDefaultCenter;
    },
  },

  data: function () {
    return {
      /* TODO: add a search mode boolean that bypasses all rendering and editing of geometries */
      /* lat, lng, and radius will only be used for search mode */
      lat: this.value && this.value.lat,
      lng: this.value && this.value.lng,
      radius: this.value && this.value.radius ? this.value.radius : 1000, // Default to 1000
      marker: null,

      mapsApiEndpoint: mapsApiEndpoint,

      geometry: this.value,

      /* TODO: need to fix attribution to pull from config */
      // attribution:
      //   '&copy; <a target="_blank" href="http://osm.org/copyright">OpenStreetMap</a> contributors',
      // osmAttribution:
      //   '&copy; <a target="_blank" href="http://osm.org/copyright">OpenStreetMap</a> contributors',

      Draw: null,

      currentDrawMode: null,

      currentFeatureCount: 0,

      currecntActiveIds: [],
    };
  },

  watch: {
    value(val, old) {
      if (this.searchMode || this.pointEditMode) {
        if (!val) {
          this.lat = undefined;
          this.lng = undefined;
          this.radius = 1000;
          return;
        }
        if (this.searchMode && typeof val.radius !== "string" && val.radius >= 0 && (!old || val.radius !== old.radius)) {
          this.radius = val.radius;
          this.addUpdateSearchRadius();
        }

        if (val.lat && (!old || val.lat !== old.lat)) {
          this.lat = val.lat;
          this.addUpdateSearchMarker(null);
        }
        if (val.lng && (!old || val.lng !== old.lng)) {
          this.lng = val.lng;
          this.addUpdateSearchMarker(null);
        }
      }
    },

    lat: { handler: "broadcast" },

    lng: { handler: "broadcast" },

    radius: { handler: "broadcast" },
  },

  mounted() {
    this.initMap();
  },

  beforeDestroy() {
    window.removeEventListener("resize", this.fixMap);
    this.map?.remove();
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
          maxZoom: 18,
        });

        this.map.addControl(new maplibregl.NavigationControl());
        this.map.addControl(new maplibregl.FullscreenControl());

        if (this.editMode) this.initDrawingTools();
        else if (this.searchMode || this.pointEditMode) this.map.on("click", this.updateLocationFromEvent);

        this.map.once("idle", () => {
          if (this.searchMode || this.pointEditMode) {
            this.addUpdateSearchMarker(null);
          } else {
            this.addGeometries();
          }

          /* concept of "others" may be reintroduced when geolocation editing is added to events */
          // if (this.others) {
          //   this.others.filter(
          //     (x) => !this.value || (x.lat != this.value.lat && x.lng != this.value.lng),
          //   ).forEach((marker)=>{
          //     new maplibregl.Marker({color: "#DDDDDD"})
          //       .setLngLat([marker.lng, marker.lat])
          //       .addTo(this.map);
          //   });
          // }
        });
      });
    },

    /* initializes the drawing tools and register drawing event listeners */
    initDrawingTools() {
      this.map.getCanvas().className = "mapboxgl-canvas maplibregl-canvas";
      this.map.getContainer().classList.add("mapboxgl-map");
      const canvasContainer = this.map.getCanvasContainer();
      canvasContainer.classList.add("mapboxgl-canvas-container");
      if (canvasContainer.classList.contains("maplibregl-interactive")) {
        canvasContainer.classList.add("mapboxgl-interactive");
      }

      this.Draw = new MapboxDraw({
        displayControlsDefault: false,
        controls: {
          polygon: true,
          point: true,
          line_string: true,
          trash: true,
        },
        defaultMode: "simple_select",
        styles: [
          {
            id: "highlight-active-points",
            type: "circle",
            filter: ["all", ["==", "$type", "Point"], ["==", "meta", "feature"], ["==", "active", "true"]],
            paint: {
              "circle-stroke-width": 2,
              "circle-stroke-color": "#FF0",
              // 'circle-color': '#088',
              "circle-opacity": 0.8,
              "circle-radius": 7,
              "circle-color": "#000000",
            },
          },
          {
            id: "points-are-blue",
            type: "circle",
            filter: ["all", ["==", "$type", "Point"], ["==", "meta", "feature"], ["==", "active", "false"]],
            paint: {
              "circle-stroke-width": 2,
              "circle-stroke-color": "#FFF",
              "circle-color": "#088",
              "circle-opacity": 0.8,
              "circle-radius": 7,
            },
          },
          // ACTIVE (being drawn)
          // line stroke
          {
            id: "gl-draw-line",
            type: "line",
            filter: ["all", ["==", "$type", "LineString"]],
            paint: {
              "line-width": 2,
              "line-color": "#088",
              "line-opacity": 0.8,
            },
          },
          // polygon fill
          {
            id: "gl-draw-polygon-fill",
            type: "fill",
            filter: ["all", ["==", "$type", "Polygon"], ["==", "active", "false"]],
            paint: {
              // "fill-color": "#D20C0C",
              // "fill-outline-color": "#D20C0C",
              // "fill-opacity": 0.1
              "fill-color": "#088",
              "fill-opacity": 0.5,
            },
          },
          {
            id: "gl-draw-polygon-fill-active",
            type: "fill",
            filter: ["all", ["==", "$type", "Polygon"], ["==", "active", "true"]],
            paint: {
              // "fill-color": "#D20C0C",
              // "fill-outline-color": "#D20C0C",
              // "fill-opacity": 0.1
              "fill-color": "#088",
              "fill-opacity": 0.2,
            },
          },
          // polygon outline stroke
          // This doesn't style the first edge of the polygon, which uses the line stroke styling instead
          {
            id: "gl-draw-polygon-stroke-active",
            type: "line",
            filter: ["all", ["==", "$type", "Polygon"], ["==", "active", "true"]],
            layout: {
              "line-cap": "round",
              "line-join": "round",
            },
            paint: {
              "line-color": "#D20C0C",
              "line-dasharray": [0.2, 2],
              "line-width": 2,
            },
          },
          {
            id: "gl-draw-polygon-stroke",
            type: "line",
            filter: ["all", ["==", "$type", "Polygon"], ["==", "active", "false"]],
            paint: {
              "line-color": "#088",
              "line-opacity": 0.8,
              "line-width": 2,
            },
          },
          // polygon mid points
          {
            id: "gl-draw-polygon-midpoint",
            type: "circle",
            filter: ["all", ["==", "$type", "Point"], ["==", "meta", "midpoint"]],
            paint: {
              "circle-radius": 3,
              "circle-color": "#000",
              "circle-stroke-width": 1,
              "circle-stroke-color": "#FFF",
            },
          },
          // vertex point halos
          {
            id: "gl-draw-polygon-and-line-vertex-halo-active",
            type: "circle",
            filter: ["all", ["==", "meta", "vertex"], ["==", "$type", "Point"]],
            paint: {
              "circle-radius": 6,
              "circle-color": "#FFF",
            },
          },
          // vertex points
          {
            id: "gl-draw-polygon-and-line-vertex-inactive",
            type: "circle",
            filter: ["all", ["==", "meta", "vertex"], ["==", "$type", "Point"], ["==", "active", "false"]],
            paint: {
              "circle-radius": 4,
              "circle-color": "#088",
              "circle-stroke-width": 1,
              "circle-stroke-color": "#000",
            },
          },
          {
            id: "gl-draw-polygon-and-line-vertex-active",
            type: "circle",
            filter: ["all", ["==", "meta", "vertex"], ["==", "$type", "Point"], ["==", "active", "true"]],
            paint: {
              "circle-radius": 5,
              "circle-color": "#088",
              "circle-stroke-width": 2,
              "circle-stroke-color": "#FF0",
            },
          },
        ],
      });
      const originalOnAdd = this.Draw.onAdd.bind(this.Draw);
      this.Draw.onAdd = (map) => {
        const controlContainer = originalOnAdd(map);
        controlContainer.classList.add("maplibregl-ctrl", "maplibregl-ctrl-group");
        return controlContainer;
      };
      this.map.addControl(this.Draw, "top-right");

      this.map.on("draw.create", (e) => {
        this.onDrawCreateOrDelete(e);
      });
      this.map.on("draw.delete", (e) => {
        this.onDrawCreateOrDelete(e);
      });
      this.map.on("draw.update", (e) => {
        this.combineFeatures(e);
      });
      this.map.on("draw.modechange", (e) => {
        this.onDrawModeChange(e);
      });
      // this.map.on('draw.selectionchange', (e) => {this.onDrawSelectionChange(e)});
      // this.map.on('draw.update', (e) => {this.onDrawUpdate(e)});
    },

    /*
     * keep track of the current editing mode and ids for geometries that are completed
     * (excluding the one that is in the process of being created)
     */
    onDrawCreateOrDelete(e) {
      if (this.Draw.getMode() != "simple_select") {
        // Update currentDrawMode if it isn't simple_select
        this.currentDrawMode = this.Draw.getMode();
      }
      this.currecntActiveIds = this.getAllFeatureIds();
      this.currentFeatureCount = this.currecntActiveIds.length;
      this.combineFeatures();
    },

    /*
     * prevent the user from adding geometries of varying base-type to the feature collection.
     * (postgis does not support feature collections in a single geometry record)
     * if the user changes drawing modes (draw_point, draw_polygon, draw_line_string) then the
     * geometries created with the previos drawing tool will cleared. the user will be prompted
     * to confirm this decision
     */
    onDrawModeChange(e) {
      if (e.mode.startsWith("draw_") && this.currentDrawMode !== e.mode) {
        if (this.currentFeatureCount > 0) {
          if (confirm("Are you sure you want to change drawing modes? The " + this.currentFeatureCount + " created feature(s) will be lost.")) {
            this.Draw.delete(this.currecntActiveIds);
            this.Draw.changeMode(e.mode);
            this.currentDrawMode = e.mode;
            this.currecntActiveIds = this.getAllFeatureIds();
            this.currentFeatureCount = this.currecntActiveIds.length;
          } else {
            this.Draw.changeMode("simple_select");
          }
        } else {
          this.currentDrawMode = e.mode;
          this.currecntActiveIds = this.getAllFeatureIds();
          this.currentFeatureCount = this.currecntActiveIds.length;
        }
      }
    },

    onDrawSelectionChange(e) {
      if (e.points.length == 1) {
        this.editingOnePoint = true;
        this.lng = e.points[0].geometry.coordinates[0];
        this.lat = e.points[0].geometry.coordinates[1];
      } else {
        this.editingOnePoint = false;
      }
    },

    onDrawUpdate(e) {
      if (e.action == "change_coordinates" && this.editingOnePoint) {
        // this.lng = e.points[0].feature[0].geometry.coordinates[0][0];
        // this.lat = e.points[0].feature[0].geometry.coordinates[0][1]
      }
    },

    /*
     * fits the map to the geometries and breaks multi geometries into single geometries
     * to allow them to be moved and edited individually
     */
    addEditableGeometries() {
      this.map.fitBounds(mapUtils.getFeatureBounds(this.geometry), {
        padding: 50,
        duration: 600,
      });
      if (this.geometry.type.includes("Multi")) {
        this.geometry.coordinates.forEach((subcoords) => {
          this.Draw.add({
            type: this.geometry.type.replace("Multi", ""),
            coordinates: subcoords,
          });
        });
      } else {
        this.Draw.add(this.geometry);
      }
    },

    /*
     * combine single geometries into multi-geometries for storage on the backend.
     */
    combineFeatures() {
      const features = this.Draw.getAll().features;

      if (features.length === 0) {
        this.$emit("input", {});
        return;
      }

      if (features.length < 2) {
        this.$emit("input", {
          type: features[0].geometry.type,
          coordinates: features[0].geometry.coordinates,
        });
        return;
      }

      const coordinates = [];
      const featureType = features[0].geometry.type.replace("Multi", "");
      for (let i = 0; i < features.length; i++) {
        const feature = features[i];
        if (feature.geometry.type.replace("Multi", "") !== featureType) {
          return;
        }
        if (feature.geometry.type.includes("Multi")) {
          feature.geometry.coordinates.forEach((subcoords) => {
            coordinates.push(subcoords);
          });
        } else {
          coordinates.push(feature.geometry.coordinates);
        }
      }

      this.$emit("input", {
        type: `Multi${featureType}`,
        coordinates,
      });
    },

    /* returns all the ids for the features on the map, excluding any that are incomplete */
    getAllFeatureIds() {
      return this.Draw.getAll()
        .features.filter((feature) => {
          return feature.geometry.coordinates.length > 0;
        })
        .map((feature) => {
          return feature.id;
        });
    },

    fixMap() {
      this.$nextTick(() => {
        if (this.map) {
          this.map.resize();
        }
      });
    },

    addGeometries() {
      if (this.geometry) {
        if (this.editMode) {
          this.addEditableGeometries();
          this.Draw.changeMode("simple_select");
          if (this.geometry.type.includes("Polygon")) {
            this.currentDrawMode = "draw_polygon";
          } else if (this.geometry.type.includes("LineString")) {
            this.currentDrawMode = "draw_line_string";
          } else if (this.geometry.type.includes("Point")) {
            this.currentDrawMode = "draw_point";
          }
          this.currecntActiveIds = this.getAllFeatureIds();
          this.currentFeatureCount = this.currecntActiveIds.length;
        } else {
          mapUtils.addGeometries(this.map, turf.feature(this.geometry));
        }
      }
    },

    clearSearchMarkerAndStyles(evt) {
      this.lat = this.lng = null;
      if (this.marker) {
        this.marker.remove();
        this.marker = null;
      }
      if (this.map.getSource("search-circle")) {
        this.map.removeLayer("search-circle-line");
        this.map.removeLayer("search-circle-fill");
        this.map.removeSource("search-circle");
      }
    },

    updateLocationFromEvent(event) {
      if (event && event.lngLat) this.lng = event.lngLat.lng;
      this.lat = event.lngLat.lat;
    },

    addUpdateSearchMarker(location) {
      if (!location) {
        if (this.lat !== undefined && this.lng !== undefined && !isNaN(parseFloat(this.lat)) && !isNaN(parseFloat(this.lng))) {
          location = [this.lng, this.lat];
        } else {
          location = [this.mapCenter.lng, this.mapCenter.lat];
        }
      }

      if ((this.searchMode || this.pointEditMode) && (!this.lat || !this.lng)) return;

      if (this.searchMode) this.addUpdateSearchRadius();

      if (!this.marker) {
        this.marker = new maplibregl.Marker({
          draggable: true,
        })
          .setLngLat(location)
          .on("dragend", (evt) => {
            const lngLat = evt.target._lngLat;
            if (this.searchMode || this.pointEditMode) {
              this.lat = lngLat.lat;
              this.lng = lngLat.lng;
              this.map.flyTo({
                center: [this.lng, this.lat],
                maxDuration: 200,
              });
            }
          })
          .addTo(this.map);
      } else {
        this.marker.setLngLat(location);
        this.map.flyTo({
          center: location,
          maxDuration: 300,
        });
      }
    },

    addUpdateSearchRadius() {
      if (!this.searchMode) {
        return;
      }

      // If radius is not provided, return
      if (!this.radius) {
        return;
      }

      if (!this.lat || !this.lng) {
        return;
      }

      var center = [this.lng, this.lat];
      var options = { steps: 90, units: "meters", properties: { mode: "search" } };
      var circle = turf.circle(center, this.radius, options);

      if (!this.map.getSource("search-circle")) {
        this.map.addSource("search-circle", {
          type: "geojson",
          data: circle,
        });
        this.map.addLayer({
          id: "search-circle-fill",
          type: "fill",
          source: "search-circle",
          filter: ["all", ["==", ["get", "mode"], "search"]],
          paint: {
            "fill-outline-color": "rgb(51, 136, 255)",
            "fill-color": "#088",
            "fill-opacity": 0.35,
          },
        });
      } else {
        this.map.getSource("search-circle").setData(circle);
      }

      debounce(() => {
        const bbox = turf.bbox(circle);
        this.map.fitBounds(bbox, { padding: 50, duration: 100 });
      }, 250)();
    },

    broadcast() {
      if (!this.searchMode && !this.pointEditMode) return;
      // Only return obj if both lat,lng values present
      if (this.lat !== undefined && this.lng !== undefined && !isNaN(parseFloat(this.lat)) && !isNaN(parseFloat(this.lng))) {
        const obj = { lat: this.lat, lng: this.lng };
        if (this.searchMode && this.radius) {
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
            <div v-if="searchMode || pointEditMode" class="d-flex" style="column-gap: 20px;">
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
              <v-btn v-if="lat&&lng" small @click="clearSearchMarkerAndStyles" text fab>
                <v-icon>mdi-close</v-icon>
              </v-btn>
            </div>

            <div v-if="searchMode">
              <v-slider
                  v-if="searchMode"
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
