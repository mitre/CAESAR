(function (e, t) {
  "object" == typeof exports && "object" == typeof module
    ? (module.exports = t())
    : "function" == typeof define && define.amd
      ? define([], t)
      : "object" == typeof exports
        ? (exports.VueTheMask = t())
        : (e.VueTheMask = t());
})(this, function () {
  return (function (e) {
    function t(r) {
      if (n[r]) return n[r].exports;
      var a = (n[r] = { i: r, l: !1, exports: {} });
      return e[r].call(a.exports, a, a.exports, t), (a.l = !0), a.exports;
    }
    var n = {};
    return (
      (t.m = e),
      (t.c = n),
      (t.i = function (e) {
        return e;
      }),
      (t.d = function (e, n, r) {
        t.o(e, n) ||
          Object.defineProperty(e, n, {
            configurable: !1,
            enumerable: !0,
            get: r,
          });
      }),
      (t.n = function (e) {
        var n =
          e && e.__esModule
            ? function () {
                return e.default;
              }
            : function () {
                return e;
              };
        return t.d(n, "a", n), n;
      }),
      (t.o = function (e, t) {
        return Object.prototype.hasOwnProperty.call(e, t);
      }),
      (t.p = "."),
      t((t.s = 10))
    );
  })([
    function (e, t) {
      e.exports = {
        "#": { pattern: /\d/ },
        X: { pattern: /[0-9a-zA-Z]/ },
        S: { pattern: /[a-zA-Z]/ },
        A: {
          pattern: /[a-zA-Z]/,
          transform: function (e) {
            return e.toLocaleUpperCase();
          },
        },
        a: {
          pattern: /[a-zA-Z]/,
          transform: function (e) {
            return e.toLocaleLowerCase();
          },
        },
        "!": { escape: !0 },
      };
    },
    function (e, t, n) {
      "use strict";
      function r(e) {
        var t = document.createEvent("Event");
        return t.initEvent(e, !0, !0), t;
      }
      var a = n(2),
        o = n(0),
        i = n.n(o);
      t.a = function (e, t) {
        var o = t.value;
        if (
          ((Array.isArray(o) || "string" == typeof o) &&
            (o = { mask: o, tokens: i.a }),
          "INPUT" !== e.tagName.toLocaleUpperCase())
        ) {
          var u = e.getElementsByTagName("input");
          if (1 !== u.length)
            throw new Error(
              "v-mask directive requires 1 input, found " + u.length,
            );
          e = u[0];
        }
        e.oninput = function (t) {
          if (t.isTrusted) {
            var i = e.selectionEnd,
              u = e.value[i - 1];
            for (
              e.value = n.i(a.a)(e.value, o.mask, !0, o.tokens);
              i < e.value.length && e.value.charAt(i - 1) !== u;

            )
              i++;
            e === document.activeElement &&
              (e.setSelectionRange(i, i),
              setTimeout(function () {
                e.setSelectionRange(i, i);
              }, 0)),
              e.dispatchEvent(r("input"));
          }
        };
        var s = n.i(a.a)(e.value, o.mask, !0, o.tokens);
        s !== e.value && ((e.value = s), e.dispatchEvent(r("input")));
      };
    },
    function (e, t, n) {
      "use strict";
      var r = n(6),
        a = n(5);
      t.a = function (e, t) {
        var o =
            !(arguments.length > 2 && void 0 !== arguments[2]) || arguments[2],
          i = arguments[3];
        return Array.isArray(t)
          ? n.i(a.a)(r.a, t, i)(e, t, o, i)
          : n.i(r.a)(e, t, o, i);
      };
    },
    function (e, t, n) {
      "use strict";
      function r(e) {
        e.component(s.a.name, s.a), e.directive("mask", i.a);
      }
      Object.defineProperty(t, "__esModule", { value: !0 });
      var a = n(0),
        o = n.n(a),
        i = n(1),
        u = n(7),
        s = n.n(u);
      n.d(t, "TheMask", function () {
        return s.a;
      }),
        n.d(t, "mask", function () {
          return i.a;
        }),
        n.d(t, "tokens", function () {
          return o.a;
        }),
        n.d(t, "version", function () {
          return c;
        });
      var c = "0.11.1";
      (t.default = r),
        "undefined" != typeof window && window.Vue && window.Vue.use(r);
    },
    function (e, t, n) {
      "use strict";
      Object.defineProperty(t, "__esModule", { value: !0 });
      var r = n(1),
        a = n(0),
        o = n.n(a),
        i = n(2);
      t.default = {
        name: "TheMask",
        props: {
          value: [String, Number],
          mask: { type: [String, Array], required: !0 },
          masked: { type: Boolean, default: !1 },
          tokens: {
            type: Object,
            default: function () {
              return o.a;
            },
          },
        },
        directives: { mask: r.a },
        data: function () {
          return { lastValue: null, display: this.value };
        },
        watch: {
          value: function (e) {
            e !== this.lastValue && (this.display = e);
          },
          masked: function () {
            this.refresh(this.display);
          },
        },
        computed: {
          config: function () {
            return {
              mask: this.mask,
              tokens: this.tokens,
              masked: this.masked,
            };
          },
        },
        methods: {
          onInput: function (e) {
            e.isTrusted || this.refresh(e.target.value);
          },
          refresh: function (e) {
            this.display = e;
            var e = n.i(i.a)(e, this.mask, this.masked, this.tokens);
            e !== this.lastValue &&
              ((this.lastValue = e), this.$emit("input", e));
          },
        },
      };
    },
    function (e, t, n) {
      "use strict";
      function r(e, t, n) {
        return (
          (t = t.sort(function (e, t) {
            return e.length - t.length;
          })),
          function (r, a) {
            for (
              var o =
                  !(arguments.length > 2 && void 0 !== arguments[2]) ||
                  arguments[2],
                i = 0;
              i < t.length;

            ) {
              var u = t[i];
              i++;
              var s = t[i];
              if (!(s && e(r, s, !0, n).length > u.length))
                return e(r, u, o, n);
            }
            return "";
          }
        );
      }
      t.a = r;
    },
    function (e, t, n) {
      "use strict";
      function r(e, t) {
        var n =
            !(arguments.length > 2 && void 0 !== arguments[2]) || arguments[2],
          r = arguments[3];
        (e = e || ""), (t = t || "");
        for (var a = 0, o = 0, i = ""; a < t.length && o < e.length; ) {
          var u = t[a],
            s = r[u],
            c = e[o];
          s && !s.escape
            ? (s.pattern.test(c) &&
                ((i += s.transform ? s.transform(c) : c), a++),
              o++)
            : (s && s.escape && (a++, (u = t[a])),
              n && (i += u),
              c === u && o++,
              a++);
        }
        for (var f = ""; a < t.length && n; ) {
          var u = t[a];
          if (r[u]) {
            f = "";
            break;
          }
          (f += u), a++;
        }
        return i + f;
      }
      t.a = r;
    },
    function (e, t, n) {
      var r = n(8)(n(4), n(9), null, null);
      e.exports = r.exports;
    },
    function (e, t) {
      e.exports = function (e, t, n, r) {
        var a,
          o = (e = e || {}),
          i = typeof e.default;
        ("object" !== i && "function" !== i) || ((a = e), (o = e.default));
        var u = "function" == typeof o ? o.options : o;
        if (
          (t &&
            ((u.render = t.render), (u.staticRenderFns = t.staticRenderFns)),
          n && (u._scopeId = n),
          r)
        ) {
          var s = u.computed || (u.computed = {});
          Object.keys(r).forEach(function (e) {
            var t = r[e];
            s[e] = function () {
              return t;
            };
          });
        }
        return { esModule: a, exports: o, options: u };
      };
    },
    function (e, t) {
      e.exports = {
        render: function () {
          var e = this,
            t = e.$createElement;
          return (e._self._c || t)("input", {
            directives: [
              {
                name: "mask",
                rawName: "v-mask",
                value: e.config,
                expression: "config",
              },
            ],
            attrs: { type: "text" },
            domProps: { value: e.display },
            on: { input: e.onInput },
          });
        },
        staticRenderFns: [],
      };
    },
    function (e, t, n) {
      e.exports = n(3);
    },
  ]);
});
