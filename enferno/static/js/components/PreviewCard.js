Vue.component("preview-card", {
  props: ["item", "value", "i18n"],
  watch: {
    value(val) {
      this.preview = val;
    },
    preview(val) {
      this.$emit("input", val);
    },
  },
  mounted() {},
  data: function () {
    return {
      preview: this.preview || false,
    };
  },

  template: `
        <v-dialog overlay="false" max-width="1000" v-model="preview">

            <v-card v-if="preview" outlined>
                <v-toolbar>
                    <v-spacer></v-spacer>
                    <v-btn outlined color="grey darken-2" @click.stop.prevent="$root.preview = false" x-small right
                           top="10" fab>
                        <v-icon>mdi-close</v-icon>
                    </v-btn>

                </v-toolbar>


                <bulletin-card :i18n="i18n" v-if="item && item.class=='bulletin'" :close="false"
                               :bulletin="item"></bulletin-card>
                <actor-card :i18n="i18n" v-else-if="item && item.class=='actor'" :close="false" :actor="item"></actor-card>
                <incident-card :i18n="i18n" v-else-if="item && item.class=='incident'" :close="false"
                               :incident="item"></incident-card>
                <organization-card :i18n="i18n" v-else-if="item && item.class=='organization'" :close="false"
                  :organization="item"></organization-card>
                <location-card :i18n="i18n" v-else-if="item" :close="false"
                               :location="item"></location-card>

            </v-card>


        </v-dialog>

    `,
});
