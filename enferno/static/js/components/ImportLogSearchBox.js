Vue.component("import-log-search-box", {
    props: {
      value: {
        type: Object,
        required: true,
      },
      i18n: {
        type: Object,
      },
    },
  
    data: () => {
      return {
        q: {},
      };
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
    created() {
      this.q = this.value;
    },
  
    template: `
        <v-sheet>
        <v-card class="pa-4">
          <v-card-title>
            Import Logs
            <v-spacer></v-spacer>
            <v-btn fab text @click="$emit('close')">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>
  
  
          <v-container class="fluid">
            <v-row>
              <v-col>
  
  
                <v-text-field
                    v-model="q.file"
                    label="File"
                    clearable
                    @keydown.enter="$emit('search',q)"
                ></v-text-field>
  
                <v-text-field
                    v-model="q.table"
                    label="Table"
                    clearable
                ></v-text-field>

                <v-text-field
                    v-model="q.status"
                    label="Status"
                    clearable
                ></v-text-field>
  
                <v-text-field
                    v-model="q.batch_id"
                    label="Batch ID"
                    clearable
                ></v-text-field>
  
                <v-text-field
                    v-model="q.format"
                    label="Format"
                    clearable
                ></v-text-field>


                </v-col>
            </v-row>
  
  
          </v-container>
  
  
        </v-card>
        <v-card tile class="text-center  search-toolbar" elevation="10" color="grey lighten-5">
          <v-card-text>
            <v-spacer></v-spacer>
            <v-btn @click="q={}" text>{{ i18n.clearSearch_ }}</v-btn>
  
            <v-btn @click="$emit('search',q)" color="primary">{{ i18n.search_ }}</v-btn>
            <v-spacer></v-spacer>
          </v-card-text>
  
        </v-card>
  
        </v-sheet>
      `,
  });
  