Vue.component("media-card", {
  props: {
    media: {},
  },
  data: function () {
    return {
      s3url: "",
    };
  },
  mounted() {
    this.init();
  },

  methods: {
    init() {
      axios
        .get(`/admin/api/media/${this.media.filename}`)
        .then((response) => {
          this.s3url = response.data;
          this.media.s3url = response.data;
        })
        .catch((error) => {
          console.error("Error fetching media:", error);
        })
        .finally(() => {
          this.$emit("ready");
        });
    },

    showPDF() {
      this.$root.$refs.pdfViewer.openPDF(this.s3url);
    },

    mediaType(mediaItem) {
      const isSafari = /constructor/i.test(window.HTMLElement) 
        || (function (p) { return p.toString() === "[object SafariRemoteNotification]"; })
        (!window['safari'] || (typeof safari !== 'undefined' && window['safari'].pushNotification));

      if (
        ["image/jpeg", "image/png", "image/gif"].includes(mediaItem.fileType)
      ) {
        return "image";
      } else if (
        ["video/webm", "video/mp4", "video/ogg"].includes(mediaItem.fileType)
      ) {
        return "video";
      } else if (["application/pdf"].includes(mediaItem.fileType)) {
        return "pdf";
      } else if (isSafari && ["image/tif", "image/tiff"].includes(mediaItem.fileType)) {
        // Only Safari supports TIF files, so display them as image files on Safari
        return "image";
      } else {
        return "unknown";
      }
    },
  },
  template: `


      <!--  Image Media Card -->
      <v-card class="pa-3" :disabled="!s3url" class="media-card " v-if="mediaType(media) == 'image'">
        <a :href="s3url"
           data-pswp-width="2000"
           data-pswp-height="2000"
           target="_blank">
          <img style="width: 215px;height: 140px; object-fit: cover" :class="{blur: media.blur}"  :src="s3url" alt=""/>
        </a>


        <div class="caption pa-1">
          {{ media.title || '&nbsp;' }}  <span v-if="media.time">({{ media.time }})</span>
        </div>
        <v-chip x-small label class="caption pa-1 " color="yellow lighten-5 grey--text">
          {{ media.etag }}
        </v-chip>
        <v-card-text class="pa-2 d-flex">
          <slot name="actions"></slot>
        </v-card-text>


      </v-card>

      <!-- Video Media Card  -->
      <v-card :disabled="!s3url" class="media-card" v-else-if="mediaType(media) == 'video'">
        <v-avatar
            tile
            class="black media-vid"
            width="100%"
            height="140px"
            @click="$emit('video-click',s3url)"
        >
          <v-icon size="52" color="#666">mdi-play-circle-outline</v-icon>
        </v-avatar>
        <div class="caption pa-2">
          {{ media.title }}
        </div>

        <div v-if="media.duration && media.duration.length" class="caption pa-2 d-flex align-center">
          <v-icon small left>mdi-timer</v-icon>
          {{ media.duration.toHHMMSS() }}

        </div>

        <!-- ETAG New Design-->
        <v-menu
            open-on-hover
            top
            offset-y
        >
          <template v-slot:activator="{ on, attrs }">
            <v-sheet v-on="on" class="etag" class="text--darken-2 ma-2 pa-2 primary--text  caption etag">
              {{ media.etag }}
            </v-sheet>
          </template>
          <v-sheet class="pa-3 caption">
            {{ media.etag }}
          </v-sheet>
        </v-menu>

        <v-card-text class="pa-2 d-flex">
          <slot name="actions"></slot>
        </v-card-text>
      </v-card>


      <!-- PDF Media Card -->
      <v-card :disabled="!s3url" class="media-card" v-else-if="mediaType(media) == 'pdf'">
        <v-btn @click="showPDF" class="mt-2" text>
          <v-icon left color="red" size="32">mdi-file-pdf-box</v-icon>
          PDF
        </v-btn>

        <div class="caption pa-2">
          {{ media.title }}
        </div>

        <!-- ETAG New Design-->
        <v-menu
            open-on-hover
            top
            offset-y
        >
          <template v-slot:activator="{ on, attrs }">
            <v-sheet v-on="on" class="etag" class="text--darken-2 ma-2 pa-2 primary--text  caption etag">
              {{ media.etag }}
            </v-sheet>
          </template>
          <v-sheet class="pa-3 caption">
            {{ media.etag }}
          </v-sheet>
        </v-menu>

        <v-card-text class="pa-2 d-flex">
          <slot name="actions"></slot>
        </v-card-text>
      </v-card>


      <!-- Other mime types   -->
      <v-card :disabled="!s3url" class="media-card" v-else-if="mediaType(media) == 'unknown'">

        <v-btn class="ma-3 py-6" :href="s3url" text target="_blank">
          <v-icon size="32" color="#666">mdi-file</v-icon>
        </v-btn>

        <div class="caption pa-2">
          {{ media.title }}
        </div>


        <!-- ETAG New Design-->
        <v-menu
            open-on-hover
            top
            offset-y
        >
          <template v-slot:activator="{ on, attrs }">
            <v-sheet v-on="on" class="etag" class="text--darken-2 ma-2 pa-2 primary--text  caption etag">
              {{ media.etag }}
            </v-sheet>
          </template>
          <v-sheet class="pa-3 caption">
            {{ media.etag }}
          </v-sheet>
        </v-menu>

        <v-card-text class="pa-2 d-flex">
          <slot name="actions"></slot>
        </v-card-text>
      </v-card>











    `,
});
