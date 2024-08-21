Vue.component("organization-result", {
  props: ["organization", "hidden", "showHide", "i18n"],

  template: `
      <template v-if="!hidden">
        <v-card outlined class="ma-2" v-if="!organization.restricted">
          <v-card-title class="d-flex">
            <v-chip label small color="gv darken-2" dark>{{ i18n.id_ }} {{ organization.id }}</v-chip>
            <v-chip color="lime darken-3" class="white--text ml-1" label small># {{ organization.originid }}</v-chip>
            <v-spacer></v-spacer>
            <v-chip v-if="organization.founded_date" small color="grey lighten-4">{{ organization.founded_date }}</v-chip>
          </v-card-title>
          <slot name="header"></slot>
          <v-card-text>

            <div class="subtitle-2 black--text mb-1 mt-2">
              {{ organization.name }}
            </div>
            <div v-html="organization.description" class="caption">
            </div>
            <v-divider class="my-2"></v-divider>
          </v-card-text>
          <v-card-actions>
            <slot name="actions"></slot>
            <v-btn v-if="showHide" @click="hidden=true" small depressed color="grey lighten-4"> {{ i18n.hide_ }}</v-btn>
            <v-btn text small icon color="gv darken-1"
                   @click.capture="$root.previewItem('/admin/api/organization/'+organization.id+'?mode=3')">
              <v-icon>mdi-eye</v-icon>
            </v-btn>
          </v-card-actions>
        </v-card>

        <v-card disabled elevation="0" v-else class="restricted">
          <v-card-text>{{ organization.id }} - Restricted</v-card-text>
        </v-card>


      </template>
    `,
});
