Vue.component("pop-date-time-field", {
  props: {
    value: {
      type: String,
      default: "",
    },
    label: {
      type: String,
    },
    timeLabel: {
      type: String,
      default: "Time",
    },
  },
  data: function () {
    return {
      dt: this.value ? dateFns.format(this.value, "YYYY-MM-DD") : null,
      tm: this.value ? dateFns.format(this.value, "HH:mm") : null,
    };
  },
  watch: {
    dt: function () {
      this.emitInput();
    },
    value: function () {
      this.dt = this.value ? dateFns.format(this.value, "YYYY-MM-DD") : null;
      this.tm = this.value ? dateFns.format(this.value, "HH:mm") : null;
    }
  },
  created() {
    //this.emitInput();
  },

  computed: {
    datetime() {
      if (this.dt) {
        if (this.tm) {
          return this.dt + "T" + this.tm;
        } else {
          return this.dt + "T00:00";
        }
      } else {
        return null;
      }
    },
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
              <pop-date-field :label="label" v-model="dt"></pop-date-field>
              <v-text-field @input="emitInput" v-model="tm" type="time" :label="timeLabel"></v-text-field>
            </div>
        </v-sheet>
    `,
});
