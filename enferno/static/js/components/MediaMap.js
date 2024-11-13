Vue.component("media-map", {
  props: {
    value: {}
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
    this.initMap();
  },

  methods: {
    initMap() {
      axios.get(`/admin/api/media/${this.value.filename}`)
        .then((response) => axios.get(`${response.data}?shapefile_group_uuid=${this.value.shapefile_group_uuid}`))
        .then((response) => {
          this.setupMap(response.data);
        });
    },

    getMapCenter(geoData) {
      const center = [0, 0]
      geoData.features.forEach((feature) => {
        center[0] += turf.centerOfMass(feature.geometry).geometry.coordinates[0];
        center[1] += turf.centerOfMass(feature.geometry).geometry.coordinates[1];
      });
      return [center[0] / geoData.features.length, center[1] / geoData.features.length];
    },

    setupMap(geoData) {
      let mlMapContainer = this.$refs.mediaMapContainer;

      mapUtils.loadBaseLayer().then((style) => {
        this.map = new maplibregl.Map({
          container: mlMapContainer,
          style: style,
          center: this.getMapCenter(geoData),
          zoom: this.zoom,
          maxZoom: 18,
        });

        this.map.on('load', () => {
          this.map.addSource('media', {
            'type': 'geojson',
            'data': geoData
          });

          this.map.addLayer({
            'id': 'mediapolygons',
            'type': 'fill',
            'source': 'media',
            'layout': {},
            'paint': {
              'fill-color': '#888888',
              'fill-outline-color': 'red',
              'fill-opacity': 0.4
            },
            'filter': ['==', '$type', 'Polygon']
          });
          this.map.addLayer({
            'id': 'mediapoints',
            'type': 'circle',
            'source': 'media',
            'layout': {},
            'paint': {
              'circle-color': '#888888',
              'circle-radius': 3,
              'circle-stroke-width': 1,
              'circle-stroke-color': 'red'
            },
            'filter': ['==', '$type', 'Point']
          });
          this.map.addLayer({
            'id': 'medialines',
            'type': 'line',
            'source': 'media',
            'layout': {},
            'paint': {
              'line-color': '#888888',
              'line-width': 2
            },
            'filter': ['==', '$type', 'LineString']
          });
        });

        this.map.addControl(new maplibregl.NavigationControl());
        this.map.addControl(new maplibregl.FullscreenControl());

        this.map.addControl(new maplibreGLMeasures.default({
          lang: {
            areaMeasurementButtonTitle: 'Measure area',
            lengthMeasurementButtonTitle: 'Measure length',
            clearMeasurementsButtonTitle: 'Clear measurements',
          },
          units: 'imperial',
          style: {
            text: {
              radialOffset: 0.9,
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
        }));

        this.map.once('render', () => {
          this.map.resize();
        });
      });
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
  },

  template: `
  <div>
    <v-card outlined color="grey lighten-3">
      <v-card-title class="headline">{{value.title}}</v-card-title>
      <v-card-text class="text-right">
        <l-map id="mediaMapContainer" ref="mediaMapContainer" :style="'position: relative; display: inline-block; height: '+ mapHeight + 'px; width: 100%;; resize: vertical'"></l-map>
        <slot name="actions"></slot>
      </v-card-text>

    </v-card>
  </div>
  `,
});
