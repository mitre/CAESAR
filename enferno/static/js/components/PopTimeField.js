Vue.component("pop-time-field", {
  props: {
    value: {
      type: String,
      default: "",
    },
    label: {
      type: String,
    },
  },
  data: function () {
    return {
      tm: this.value ? dateFns.format(this.value, "HH:mm") : null,
    };
  },
  watch: {
    tm: function () {
      this.emitInput();
    },
    value: function () {
      this.tm = this.value ? dateFns.format(this.value, "HH:mm") : null;
    }
  },
  created() {
    //this.emitInput();
  },

  computed: {
  },

  methods: {
    emitInput() {
      if (dateFns.isValid(dateFns.parse(this.datetime))) {
        this.$emit("input", this.datetime);
      } else {
        this.$emit("input", null);
      }
    },
  },

  template: `
        <v-sheet>
          <div style="display: flex; gap: 8px">
              <v-text-field @input="emitInput" v-model="tm" type="time" :label="label"></v-text-field>
            </div>
        </v-sheet>
    `,
});
