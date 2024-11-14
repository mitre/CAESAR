Vue.component("organization-card", {
  props: [
    "organization",
    "close",
    "thumb-click",
    "active",
    "log",
    "diff",
    "showEdit",
    "i18n",
  ],

  watch: {
    organization: function (b, n) {
      this.loadBulletinRelations();
      this.loadActorRelations();
      this.loadIncidentRelations();
      this.loadOrganizationRelations();
      this.mapLocations = aggregateOrganizationLocations(this.organization);
    },
  },

  mounted() {
    if(this.organization) this.mapLocations = aggregateOrganizationLocations(this.organization);
  },

  methods: {
    updateMediaState() {
      this.mediasReady += 1;
      if (
        this.mediasReady == this.organization.medias.length &&
          this.mediasReady > 0
      ) {
        this.prepareImagesForPhotoswipe().then((res) => {
          this.initLightbox();
        });
      }
    },

    prepareImagesForPhotoswipe() {
      // Get the <a> tags from the image gallery
      const imagesList = document.querySelectorAll("#lightbox a");
      const promisesList = [];

      imagesList.forEach((element) => {
        const promise = new Promise(function (resolve) {
          let image = new Image();
          image.src = element.getAttribute("href");
          image.onload = () => {
            element.dataset.pswpWidth = image.width;
            element.dataset.pswpHeight = image.height;
            resolve(); // Resolve the promise only if the image has been loaded
          };
          image.onerror = () => {
            resolve();
          };
        });
        promisesList.push(promise);
      });

      // Use .then() to handle the promise resolution
      return Promise.all(promisesList);
    },

    initLightbox() {
      this.lightbox = new PhotoSwipeLightbox({
        gallery: "#lightbox",
        children: "a",
        pswpModule: PhotoSwipe,
        wheelToZoom: true,
        arrowKeys: true,
      });

      this.lightbox.init();
    },

    translate_status(status) {
      return translate_status(status);
    },

    loadBulletinRelations(page = 1) {
      // b2a
      axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=bulletin&page=${page}`,
        )
        .then((res) => {
          this.organization.bulletin_relations = res.data.items;
          this.bulletinPage += 1;
          this.bulletinLM = res.data.more;
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },

    loadActorRelations(page = 1) {
      axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=actor&page=${page}`,
        )
        .then((res) => {
          this.organization.actor_relations = res.data.items;
          this.actorPage += 1;
          this.actorLM = res.data.more;
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },

    loadIncidentRelations(page = 1) {
      // b2i
      axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=incident&page=${page}`,
        )
        .then((res) => {
          this.organization.incident_relations = res.data.items;
          this.incidentPage += 1;
          this.incidentLM = res.data.more;
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },

    loadOrganizationRelations(page = 1) {
      // b2i
      axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=organization&page=${page}`,
        )
        .then((res) => {
          this.organization.organization_relations = res.data.items;
          this.organizationPage += 1;
          this.organizationLM = res.data.more;
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },

    probability(item) {
      return translations.probs[item.probability].tr;
    },

    logAllowed() {
      return this.$root.currentUser.view_simple_history && this.log;
    },

    diffAllowed() {
      return this.$root.currentUser.view_full_history && this.diff;
    },

    editAllowed() {
      return this.$root.editAllowed(this.organization) && this.showEdit;
    },

    deleteAllowed() {
      return this.$root.has_role(this.$root.currentUser, "Admin") && this.showEdit;
    },

    deleteOrganization() {
      this.$emit("delete", this.organization);
      this.$emit("close")
    },

    removeVideo() {
      let video = this.$el.querySelector("#iplayer video");
      if (video) {
        video.remove();
      }
    },

    viewThumb(s3url) {
      this.$emit("thumb-click", s3url);
    },

    viewVideo(s3url) {
      this.removeVideo();

      let video = document.createElement("video");
      video.src = s3url;
      video.controls = true;
      video.autoplay = true;
      this.$el.querySelector("#iplayer").append(video);
    },

    loadRevisions() {
      this.hloading = true;
      if (this.revisions && this.revisions.length > 0) {
        this.revisions = null;
        this.hloading = false;
        return;
      }
      axios
        .get(`/admin/api/organizationhistory/${this.organization.id}`)
        .then((response) => {
          this.revisions = response.data.items;
        })
        .catch((error) => {
          console.log(error.body.data);
        })
        .finally(() => {
          this.hloading = false;
        });
    },

    showDiff(e, index) {
      this.diffDialog = true;
      //calculate diff
      const dp = jsondiffpatch.create({
        arrays: {
          detectMove: true,
        },
        objectHash: function (obj, index) {
          return obj.name || obj.id || obj._id || "$$index:" + index;
        },
      });

      const delta = dp.diff(
        this.revisions[index + 1].data,
        this.revisions[index].data,
      );
      if (!delta) {
        this.diffResult = "Both items are Identical :)";
      } else {
        this.diffResult = jsondiffpatch.formatters.html.format(delta);
      }
    },
    loadAllBulletinRelations(page = 1) {
      if (page === 1) {
        this.organization.bulletin_relations = [];
      }
      return axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=bulletin&page=${page}`,
        )
        .then((res) => {
          this.organization.bulletin_relations.push.apply(
            this.organization.bulletin_relations,
            res.data.items,
          );
          if (res.data.more) {
            page += 1;
            return this.loadAllBulletinRelations(page);
          } else {
            this.bulletinLM = false;
            this.bulletinPage = page;
          }
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },
    loadAllActorRelations(page = 1) {
      if (page === 1) {
        this.organization.actor_relations = [];
      }
      return axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=actor&page=${page}`,
        )
        .then((res) => {
          this.organization.actor_relations.push.apply(
            this.organization.actor_relations,
            res.data.items,
          );
          if (res.data.more) {
            page += 1;
            return this.loadAllActorRelations(page);
          } else {
            this.actorLM = false;
            this.actorPage = page;
          }
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },
    loadAllOrganizationRelations(page = 1) {
      if (page === 1) {
        this.organization.organization_relations = [];
      }
      return axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=organization&page=${page}`,
        )
        .then((res) => {
          this.organization.organization_relations.push.apply(
            this.organization.organization_relations,
            res.data.items,
          );
          if (res.data.more) {
            page += 1;
            return this.loadAllOrganizationRelations(page);
          } else {
            this.organizationLM = false;
            this.organizationPage = page;
          }
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },
    loadAllIncidentRelations(page = 1) {
      if (page === 1) {
        this.organization.incident_relations = [];
      }
      return axios
        .get(
          `/admin/api/organization/relations/${this.organization.id}?class=incident&page=${page}`,
        )
        .then((res) => {
          this.organization.incident_relations.push.apply(
            this.organization.incident_relations,
            res.data.items,
          );
          if (res.data.more) {
            page += 1;
            return this.loadAllIncidentRelations(page);
          } else {
            this.incidentLM = false;
            this.incidentPage = page;
          }
        })
        .catch((err) => {
          console.log(err.toJSON());
        });
    },
    closeVisualization() {
      // Reload the bulletin relations
      this.bulletinPage = 1;
      this.organization.bulletin_relations = [];
      this.bulletinLM = true;
      this.loadBulletinRelations(this.bulletinPage);
      
      // Reload the Actor relations
      this.actorPage = 1;
      this.organization.actor_relations = [];
      this.actorLM = true;
      this.loadActorRelations(this.actorPage);
      
      // Reload the Organization relations
      this.organizationPage = 1;
      this.organization.organization_relations = [];
      this.organizationLM = true;
      this.loadOrganizationRelations(this.organizationPage);
      
      // Reload the Incident relations
      this.incidentPage = 1;
      this.organization.incident_relations = [];
      this.incidentLM = true;
      this.loadIncidentRelations(this.incidentPage);
    },
    async visualize() {
      // Load all the relations
      await this.loadAllBulletinRelations();
      await this.loadAllActorRelations();
      await this.loadAllOrganizationRelations();
      await this.loadAllIncidentRelations();

      this.$root.$refs.viz.visualize(this.organization, this.closeVisualization)
    }
  },

  data: function () {
    return {
      diffResult: "",
      diffDialog: false,
      revisions: null,
      show: false,
      hloading: false,
      mapLocations: [],

      lightbox: null,
      mediasReady: 0,

      // pagers for related entities
      bulletinPage: 1,
      actorPage: 1,
      incidentPage: 1,
      organizationPage: 1,

      // load more buttons
      bulletinLM: false,
      actorLM: false,
      incidentLM: false,
      organizationLM: false,
    };
  },

  template: `

  <v-card color="grey lighten-3" class="mx-auto pa-3">
    <v-card color="grey lighten-5" outlined class="header-fixed mx-2">
      <v-btn v-if="close" @click="$emit('close',$event.target.value)" fab absolute top right x-small text class="mt-6">
        <v-icon>mdi-close</v-icon>
      </v-btn>
      <v-card-text class="d-flex align-center">
        <v-chip small pill label color="gv darken-2" class="white--text">
          {{ i18n.id_ }} {{ organization.id }}</v-chip>

        <v-chip :href="organization.source_link" target="_blank" small pill label color="lime darken-3 "
          class="white--text ml-1">
          # {{ organization.originid }}</v-chip>
        <v-btn v-if="editAllowed()" class="ml-2" @click="$emit('edit',organization)" small outlined><v-icon color="primary" left>mdi-pencil</v-icon> {{ i18n.edit_ }}</v-btn>
        <v-btn @click.stop="visualize()" class="ml-2" outlined small elevation="0"><v-icon color="primary" left>mdi-graph-outline</v-icon> {{ i18n.visualize_ }}</v-btn>
      </v-card-text>

      <v-btn v-if="deleteAllowed()" class="ml-2 red darken-3" @click="deleteOrganization" small outlined>
        <v-icon color="white" left>mdi-archive</v-icon>
        <span class="white--text">{{ i18n.archive_ }}</span>
      </v-btn>

      <v-chip color="blue-grey lighten-5" label small class="pa-2 mx-2 my-2" v-if="organization.assigned_to" ><v-icon left>mdi-account-circle-outline</v-icon>
        {{ i18n.assignedUser_ }} {{organization.assigned_to['name']}}</v-chip>
      <v-chip color="blue-grey lighten-5" small label class="mx-2 my-2" v-if="organization.status" > <v-icon left>mdi-delta</v-icon> {{ organization.status }}</v-chip>
    </v-card>

    <v-card v-if="organization.roles?.length" color="blue darken-1" class="ma-2 pa-2 d-flex align-center flex-grow-1" elevation="0">
      <v-icon content="Access Roles" v-tippy color="white">mdi-lock</v-icon>
      <v-chip label color="gray darken-3" small v-for="role in organization.roles"  :color="role.color" class="caption mx-1">{{ role.name }}</v-chip>

    </v-card>

    <v-card outlined class="ma-2" color="grey lighten-5">
      <v-card-text>
        <h2 class="title black--text d-block">{{ organization.name }}</h2>

        <div class="organization-description" v-html="organization.description"></div>
      </v-card-text>

    </v-card>

    <div class="d-flex" v-if="organization.credibility">
      <uni-field :caption="i18n.credibility_" :english="organization._credibility"></uni-field>
    </div>

    <!-- Map -->
    <v-card outlined class="ma-2 pa-2" color="grey lighten-5">
      <global-map :i18n="i18n" :value="mapLocations"></global-map>
    </v-card>

    <!-- Roles Within -->
    <v-card outlined class="ma-2" color="grey lighten-5" v-if="organization.roles_within && organization.roles_within.length">
      <v-card-text>
        <div class="px-1 title black--text">{{ i18n.rolesWithin_ }}</div>
        <v-card v-for="role in organization.roles_within" class="mt-3">
          <v-card-text class="py-2">
            <p> <b> {{role.title}} </b> </p>
            <p> <b> Reports To: </b> <span v-if="role.reports_to_title">{{role.reports_to_title}}</span> <span v-else> None </span> </p>
            <p> <b> <span v-if="!role.currently_active"> Not </span> Active </b> </p>
            <p v-for="actor in role.actors"> 
              {{actor.actor_name}}
              <span v-if="actor.from_date"> ({{actor.from_date}} - <span v-if="actor.to_date"> {{actor.to_date}} </span> <span v-else> present</span>) </span>
            </p>
          </v-card-text>
        </v-card>
      </v-card-text>
    </v-card>

    <v-card outlined class="ma-2" color="grey lighten-5" v-if="organization.events && organization.events.length">
      <v-card-text>
        <div class="px-1 title black--text">{{ i18n.events_ }}</div>
        <event-card v-for="event in organization.events" :key="event.id" :event="event"></event-card>
      </v-card-text>
    </v-card>
    <!-- Related Organization -->
    <v-card outlined color="grey lighten-5" class="ma-2" v-if="organization.organization_relations && organization.organization_relations.length">

      <v-card-text>
        <div class="pa-2 header-sticky title black--text">{{ i18n.relatedOrganizations_ }}
          <v-tooltip top>
            <template v-slot:activator="{on,attrs}">
              <a :href="'/admin/actors/?reltoo='+organization.id" target="_self">
                <v-icon v-on="on" small color="grey" class="mb-1">
                  mdi-image-filter-center-focus-strong
                </v-icon>
              </a>
            </template>
            <span>Filter and display related items in main table</span>
          </v-tooltip>
        </div>
        <organization-result :i18n="i18n" class="mt-1" v-for="(item,index) in organization.organization_relations" :key="index"
          :organization="item.organization">
          <template v-slot:header>

            <v-sheet color="yellow lighten-5" class="pa-2">

              <div class="caption ma-2">{{ i18n.relationshipInfo_ }}</div>
              <v-chip v-if="item.probability!== null" class="ma-1" color="grey lighten-4" small label>
                {{ probability(item) }}
              </v-chip>
              <v-chip class="ma-1" v-for="r in extractValuesById($root.otooInfo, item.related_as, 'title')"
                color="grey lighten-4" small
                label>{{ r }}
              </v-chip>
              <v-chip v-if="item.comment" class="ma-1" color="grey lighten-4" small label>{{ item.comment }}
              </v-chip>

            </v-sheet>
          </template>
        </organization-result>
      </v-card-text>
      <v-card-actions>
        <v-btn class="ma-auto caption" small color="blue-grey lighten-5" elevation="0" @click="loadOrganizationRelations(organizationPage)" v-if="organizationLM">Load More <v-icon right>mdi-chevron-down</v-icon> </v-btn>
      </v-card-actions>
    </v-card>

    <v-card outlined color="grey lighten-5" class="ma-2" v-if="organization.bulletin_relations && organization.bulletin_relations.length">

      <v-card-text>
        <div class="pa-2 header-sticky title black--text">{{ i18n.relatedBulletins_ }}
          <v-tooltip top>
            <template v-slot:activator="{on,attrs}">

              <a :href="'/admin/primary-records/?reltoo='+organization.id" target="_self"><v-icon v-on="on" small color="grey" class="mb-1">
                mdi-image-filter-center-focus-strong
              </v-icon></a>
            </template>
            <span>Filter and display related items in main table</span>
          </v-tooltip>
        </div>
        <bulletin-result :i18n="i18n"  class="mt-1" v-for="(item,index) in organization.bulletin_relations" :key="index"
          :bulletin="item.bulletin">
          <template v-slot:header>

            <v-sheet color="yellow lighten-5" class="pa-2">

              <div class="caption ma-2">{{ i18n.relationshipInfo_ }}</div>
              <v-chip v-if="item.probability!=null" class="ma-1" color="blue-grey lighten-5" small label>{{ probability(item) }}</v-chip>
              <v-chip class="ma-1" v-for="rel in extractValuesById($root.otobInfo,item.related_as,'title')" color="blue-grey lighten-5" small label>{{ rel }}</v-chip>
              <v-chip v-if="item.comment" class="ma-1" color="blue-grey lighten-5" small label>{{ item.comment }}</v-chip>

            </v-sheet>

          </template>
        </bulletin-result>
      </v-card-text>
      <v-card-actions>
        <v-btn class="ma-auto caption" small color="blue-grey lighten-5" elevation="0" @click="loadBulletinRelations(bulletinPage)" v-if="bulletinLM">Load More <v-icon right>mdi-chevron-down</v-icon> </v-btn>
      </v-card-actions>
    </v-card>

    <v-card outlined color="grey lighten-5" class="ma-2" v-if="organization.actor_relations && organization.actor_relations.length">

      <v-card-text>
        <div class="pa-2 header-sticky title black--text">{{ i18n.relatedActors_ }}
          <v-tooltip top>
            <template v-slot:activator="{on,attrs}">

              <a :href="'/admin/primary-records/?reltoo='+organization.id" target="_self"><v-icon v-on="on" small color="grey" class="mb-1">
                mdi-image-filter-center-focus-strong
              </v-icon></a>
            </template>
            <span>Filter and display related items in main table</span>
          </v-tooltip>
        </div>
        <actor-result :i18n="i18n"  class="mt-1" v-for="(item,index) in organization.actor_relations" :key="index"
          :actor="item.actor">
          <template v-slot:header>

            <v-sheet color="yellow lighten-5" class="pa-2">

              <div class="caption ma-2">{{ i18n.relationshipInfo_ }}</div>
              <v-chip v-if="item.probability!=null" class="ma-1" color="blue-grey lighten-5" small label>{{ probability(item) }}</v-chip>
              <v-chip class="ma-1" v-for="rel in extractValuesById($root.otobInfo,item.related_as,'title')" color="blue-grey lighten-5" small label>{{ rel }}</v-chip>
              <v-chip v-if="item.comment" class="ma-1" color="blue-grey lighten-5" small label>{{ item.comment }}</v-chip>

            </v-sheet>

          </template>
        </actor-result>
      </v-card-text>
      <v-card-actions>
        <v-btn class="ma-auto caption" small color="blue-grey lighten-5" elevation="0" @click="loadactorRelations(actorPage)" v-if="actorLM">Load More <v-icon right>mdi-chevron-down</v-icon> </v-btn>
      </v-card-actions>
    </v-card>

    <v-card outlined color="grey lighten-5" class="ma-2" v-if="organization.incident_relations && organization.incident_relations.length">
      <v-card-text>
        <div class="pa-2  header-sticky title black--text">{{ i18n.relatedIncidents_ }}
          <v-tooltip top>
            <template v-slot:activator="{on,attrs}">
              <a :href="'/admin/investigations/?reltoo='+organization.id" target="_self">
                <v-icon v-on="on" small color="grey" class="mb-1">
                  mdi-image-filter-center-focus-strong
                </v-icon>
              </a>
            </template>
            <span>Filter and display related items in main table</span>
          </v-tooltip>
        </div>
        <incident-result :i18n="i18n"  class="mt-1" v-for="(item,index) in organization.incident_relations" :key="index"
          :incident="item.incident">
          <template v-slot:header>

            <v-sheet color="yellow lighten-5" class="pa-2">

              <div class="caption ma-2">{{ i18n.relationshipInfo_ }}</div>
              <v-chip v-if="item.probability!=null" class="ma-1" color="blue-grey lighten-5" small label>{{ probability(item) }}</v-chip>
              <v-chip class="ma-1" v-for="rel in extractValuesById($root.otoiInfo, item.related_as, 'title')" color="blue-grey lighten-5" small label>{{ rel }}</v-chip>
              <v-chip v-if="item.comment" class="ma-1" color="blue-grey lighten-5" small label>{{ item.comment }}</v-chip>

            </v-sheet>

          </template>
        </incident-result>
      </v-card-text>
      <v-card-actions>
        <v-btn class="ma-auto caption" small color="blue-grey lighten-5" elevation="0" @click="loadIncidentRelations(incidentPage)" v-if="incidentLM">Load More <v-icon right>mdi-chevron-down</v-icon> </v-btn>
      </v-card-actions>
    </v-card>

    <v-card v-if="organization.status==='Peer Reviewed'" outline elevation="0" class="ma-2" color="light-green lighten-5">
      <v-card-text>
        <div class="px-1 title black--text">{{ i18n.review_ }}</div>
        <div v-html="organization.review" class="pa-1 my-2 grey--text text--darken-2">

        </div>
        <v-chip small label color="lime">{{ organization.review_action }}</v-chip>
      </v-card-text>
    </v-card>

    <!-- Log -->
    <v-card v-if="logAllowed()" outline elevation="0" class="ma-2">
      <v-card-text>
        <h3 class="title black--text align-content-center">{{ i18n.logHistory_ }}
          <v-btn fab :loading="hloading" @click="loadRevisions" small class="elevation-0 align-content-center">
            <v-icon>mdi-history</v-icon>
          </v-btn>
        </h3>

        <template v-for="(revision,index) in revisions">
          <v-card color="grey lighten-4" dense flat class="my-1 pa-2 d-flex align-center">
            <span class="caption">{{ revision.data['comments'] }} - <v-chip x-small label
              color="gv lighten-3">{{ translate_status(revision.data.status) }}</v-chip> - {{ revision.created_at }}
              - By {{ revision.user.username }}</span>
            <v-spacer></v-spacer>

            <v-btn v-if="diffAllowed()" v-show="index!==revisions.length-1" @click="showDiff($event,index)" class="mx-1"
              color="grey" icon small>
              <v-icon>mdi-compare</v-icon>
            </v-btn>

          </v-card>

        </template>
      </v-card-text>

    </v-card>
    <v-dialog
      v-model="diffDialog"
      max-width="770px"
    >
      <v-card class="pa-5">
        <v-card-text>
          <div v-html="diffResult">
          </div>
        </v-card-text>
      </v-card>

    </v-dialog>


    <!-- Root Card   -->
  </v-card>
  `,
});
