Vue.component("pop-date-field", {
  props: ["value", "label", "disabled"],

  data() {
    return {
      id: null,
      menu: false,
      pickerDate: this.value,
      textDate: this.value,
      errorMsg: null,
    };
  },

  created() {
    this.id = "date" + this._uid;
    this.$emit("input", this.value);
  },

  methods: {
    formatDate(s) {
      // Check if the string matches the 'YYYY-MM-DDTHH:MM' format
      const pattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

      if (pattern.test(s)) {
        return s.split("T")[0];
      } else {
        return s;
      }
    },

    isValidDate() {
      if (!this.pickerDate) return true;

      const regex = /^(19\d\d|20[0-3]\d|2040)-\d{2}-\d{2}$/;
      const dateString = this.pickerDate.trim();

      if (!regex.test(dateString)) {
        this.errorMsg = "Must be >1900 and <2040";
        return false;
      }

      if (isNaN(new Date(dateString).getTime())) {
        this.errorMsg = "Invalid date format";
        return false;
      }

      return true; // Valid date
    },

    dateInputFieldEdited() {
      this.errorMsg = null;

      if (this.pickerDate && this.isValidDate()) {
        this.$emit("input", this.pickerDate);
      }
    },
  },

  watch: {
    pickerDate(val) {
      this.$emit("input", val);
    },

    textDate(val, old) {
      this.$emit("input", val);
      if (val !== old) {
        this.pickerDate = val;
      }
    },

    value(val, old) {
      if (val !== old) {
        this.textDate = this.formatDate(val);
        this.pickerDate = val;
      }
    },
  },

  template: `
      <v-menu
          v-model="menu"
          ref="dateMenu"
          transition="scale-transition"
          offset-y
          max-width="290px"
          min-width="290px"
          :close-on-content-click="false"
          :disabled="disabled"
      >
      <template v-slot:activator="{ on, attrs }">
        <v-text-field
            @click:prepend="menu=true"
            v-model="textDate"
            type="date"
            min="1900-01-01"
            max="2040-01-01"
            placeholder="YYYY-MM-DD"
            onClick="event.preventDefault()"
            v-bind="attrs"
            :label="label"
            persistent-hint
            prepend-icon="mdi-calendar"
            clearable
            @blur="dateInputFieldEdited"
            :disabled="disabled"
            :error-messages="errorMsg"
        />
      </template>

      <v-date-picker
          scrollable
          no-title
          min="1900-01-01"
          max="2040-01-01"
          v-model="pickerDate"
          :disabled="disabled"
          @input="menu = false">
      </v-date-picker>
      </v-menu>
    `,
});
