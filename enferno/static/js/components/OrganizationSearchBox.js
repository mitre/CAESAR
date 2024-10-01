Vue.component("organization-search-box", {
  props: {
    value: {
      type: Object,
      required: true,
    },
    users: {
      type: Array,
    },
    roles: {
      type: Array,
    },

    extraFilters: {
      type: Boolean,
    },
    showOp: {
      type: Boolean,
      default: true,
    },
    i18n: {
      type: Object,
    },

    isAdmin: {
      type: Boolean,
      default: false,
    },
  },

  data: () => {
    return {
      translations: translations,
      searches: [],
      saveDialog: false,
      repr: "",
      q: {},
      qName: "",
      organizationTypes: [],
    };
  },

  created() {
    this.q = this.value;
  },

  mounted() {
    this.q.locTypes = this.translations.organizationLocTypes_.map((x) => x.code);
    axios.get(`/admin/api/organization-types/`).then(response => {
      this.organizationTypes = response.data.items;
    }).catch(error => {
        this.organizationTypes = [];
        console.error(error.message);
      });
  },

  watch: {
    q: {
      handler(newVal) {
        this.$emit("input", newVal);
      },
      deep: true,
    },
    value: function (newVal, oldVal) {
      if (newVal !== oldVal) {
        this.q = newVal;
      }
    },
  },

  computed: {
    showGeomap() {
      return this.q.locTypes?.length > 0;
    },
  },

  methods: {},

  template: `
  <v-card flat>
    <v-card-text>
      <v-container class="fluid">
        <v-row v-if="showOp">
          <v-col>
            <v-btn-toggle mandatory v-model="q.op">
              <v-btn small value="and">And</v-btn>
              <v-btn small value="or">Or</v-btn>
            </v-btn-toggle>
          </v-col>
        </v-row>
        <v-row>
          <v-col>

            <v-text-field
              v-model="q.tsv"
              :label="i18n.contains_"
              clearable
              @keydown.enter="$emit('search',q)"
            ></v-text-field>

            <v-text-field

              v-model="q.extsv"
              :label="i18n.notContains_"
              clearable
            ></v-text-field>
          </v-col>
        </v-row>
        <v-row>
          <v-col md="6">
            <div class="d-flex flex-wrap">
              <pop-date-range-field
                ref="foundedDateComponent"
                :label="i18n.foundedDate_"
                v-model="q.foundedDate"
              />
            </div>
          </v-col>
        </v-row>
        <v-row v-if="extraFilters">
          <v-col cols="12">
            <span class="caption">{{ i18n.createdBy_ }}</span>
            <v-chip-group
              column
              multiple
              v-model="q.created_by"
            >
              <v-chip :value="user.id" label small v-for="user in users" filter
                outlined>{{ user.name }}
              </v-chip>
            </v-chip-group>
          </v-col>
        </v-row>
        <v-row>
          <v-col cols="12">
            <span class="caption">Type</span>
            <v-select :items="organizationTypes" label="Type"
              v-model="q.types" item-text="title" return-object
              clearable></v-select>
          </v-col>
        </v-row>
        <v-row>
          <v-col md="12">
            <v-alert text color="grey lighten-1" class="pa-5 my-3">
              <div class="d-flex align-baseline justify-lg-space-between" >

                <span class="black--text font-weight-bold text-h6">Events</span>
                <v-checkbox :label="i18n.singleEvent_" dense v-model="q.singleEvent" color="primary" small
                  class="ma-3"></v-checkbox>
              </div>
              <div class="d-flex align-baseline"  > 
                <pop-date-range-field
                  :label="i18n.eventDate_"
                  v-model="q.edate"

                  class="mt-2"

                />
              </div>
              <location-search-field
                v-model="q.elocation"
                api="/admin/api/locations/"
                item-text="full_string"
                item-value="id"
                :multiple="false"
                :label="i18n.includeEventLocations_"
              ></location-search-field>




            </v-alert>

          </v-col>
        </v-row>

        <v-row v-if="isAdmin" > 
          <v-col md="9">
            <span class="caption">Access Roles</span>
            <v-chip-group
              column
              multiple
              v-model="q.roles"                                
            >
              <v-chip v-if="roles" :value="role.id" small v-for="role in roles" filter
                outlined>{{role.name}}</v-chip>
            </v-chip-group>
          </v-col>
          <v-col md="3">
            <span class="caption">Unrestricted</span>
            <v-switch v-model="q.norole"></v-switch>
          </v-col>
        </v-row>


        <v-row v-if="extraFilters">

          <v-col md="9">
            <span class="caption">{{i18n.assignedUser_}}</span>


            <v-chip-group
              column
              multiple
              v-model="q.assigned"

            >
              <v-chip :value="user.id" small label v-if="user.name != ''" v-for="user in users" filter
                outlined>{{user.name}}</v-chip>
            </v-chip-group>
          </v-col>
          <v-col md="3">
            <span class="caption">{{ i18n.unassigned_ }}</span>
            <v-switch v-model="q.unassigned"></v-switch>
          </v-col>
        </v-row>

        <v-row v-if="extraFilters">
          <v-col cols="12">
            <span class="caption">{{ i18n.reviewer_ }}</span>

            <v-chip-group
              column
              multiple
              v-model="q.reviewer"
            >
              <v-chip :value="user.id" label small v-if="user.name != ''" v-for="user in users" filter
                outlined>{{user.name}}</v-chip>
            </v-chip-group>
          </v-col>
        </v-row>


        <v-row v-if="extraFilters">
          <v-col cols="12">
            <span class="caption pt-2">{{ i18n.workflowStatus_ }}</span>


            <v-chip-group
              column
              multiple
              v-model="q.statuses"
            >
              <v-chip :value="status.en" label small v-for="status in translations.statuses"
                filter outlined :key="status.en">{{status.tr}}</v-chip>
            </v-chip-group>

          </v-col>
        </v-row>

        <v-row>
          <v-col cols="12">
            <span class="caption pt-2">{{ i18n.reviewAction_ }}</span>
            <v-chip-group column v-model="q.reviewAction">
              <v-chip value="No Review Needed" label small filter outlined >No Review Needed</v-chip>
              <v-chip value="Needs Review" label small filter outlined>Needs Review</v-chip>

            </v-chip-group>

          </v-col>
        </v-row>
        <v-row>
          <v-col>
            <div class="d-flex">
              <location-search-field
                v-model="q.locations"
                api="/admin/api/locations/"
                item-text="full_string"
                item-value="id"
                :multiple="true"
                :label="i18n.includeLocations_"

              ></location-search-field>
              <v-checkbox :label="i18n.any_" dense v-model="q.oplocations" color="primary" small
                class="mx-3"></v-checkbox>
            </div>
            <location-search-field
              v-model="q.exlocations"
              api="/admin/api/locations/"
              item-text="full_string"
              item-value="id"
              :multiple="true"
              :label="i18n.excludeLocations_"
              :post-request="true"
            ></location-search-field>


          </v-col>
        </v-row>

        <v-text-field
          v-model="q.tsv"
          label="Title"
          clearable
          @keydown.enter="$emit('search',q)"
        ></v-text-field>
      </v-container>
    </v-card-text>

  </v-card>



  `,
});
