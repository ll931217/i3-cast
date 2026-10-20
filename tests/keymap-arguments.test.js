const test = require("node:test")
const assert = require("node:assert")
const Keymap = require("../plugin/core/Keymap.js")
const Args = require("../plugin/core/Arguments.js")
const RootSearch = require("../plugin/core/RootSearch.js")
const { createSettingsProvider } = require("../plugin/core/SettingsProvider.js")

const ctrl = { ctrl: true, shift: false, alt: false }

test("emacs keys", () => {
  assert.strictEqual(Keymap.resolve("emacs", ctrl, "k", false), "actions")
  assert.strictEqual(Keymap.resolve("emacs", ctrl, "n", false), "down")
  assert.strictEqual(Keymap.resolve("emacs", ctrl, "p", false), "up")
  assert.strictEqual(Keymap.resolve("emacs", ctrl, "j", false), "")
})

test("ctrl+p is the dropdown only when the view has one", () => {
  assert.strictEqual(Keymap.resolve("emacs", ctrl, "p", true), "dropdown")
  assert.strictEqual(Keymap.resolve("vim-motions", ctrl, "p", true), "dropdown")
})

test("vim motions move ctrl+k to up and the action panel to ctrl+shift+k", () => {
  assert.strictEqual(Keymap.resolve("vim-motions", ctrl, "k", false), "up")
  assert.strictEqual(Keymap.resolve("vim-motions", ctrl, "j", false), "down")
  assert.strictEqual(Keymap.resolve("vim-motions", ctrl, "h", false), "back")
  assert.strictEqual(Keymap.resolve("vim-motions", ctrl, "l", false), "open")
  for (const mode of ["emacs", "vim-motions"])
    assert.strictEqual(Keymap.resolve(mode, { ctrl: true, shift: true, alt: false }, "k", false), "actions")
})

test("ctrl+t is the toast; alt and plain keys are not commands", () => {
  assert.strictEqual(Keymap.resolve("emacs", ctrl, "t", false), "toast")
  assert.strictEqual(Keymap.resolve("emacs", { ctrl: true, shift: false, alt: true }, "k", false), "")
  assert.strictEqual(Keymap.resolve("emacs", { ctrl: false, shift: false, alt: false }, "k", false), "")
})

const specs = [
  { placeholder: "Name", type: "text", optional: false },
  { placeholder: "Mood", type: "dropdown", optional: true, data: ["happy", "sad"] },
  { placeholder: "Secret", type: "password", optional: false }
]

test("typing and backspace edit one pill", () => {
  let v = Args.initialValues(specs)
  v = Args.typeText(v, 0, specs, "A")
  v = Args.typeText(v, 0, specs, "n")
  assert.deepStrictEqual(v, ["An", "", ""])
  assert.deepStrictEqual(Args.backspace(v, 0), ["A", "", ""])
  assert.deepStrictEqual(Args.typeText(v, 1, specs, "x"), v)
})

test("optional dropdown cycles through no value and each option", () => {
  let v = Args.initialValues(specs)
  v = Args.cycle(v, 1, specs, 1); assert.strictEqual(v[1], "happy")
  v = Args.cycle(v, 1, specs, 1); assert.strictEqual(v[1], "sad")
  v = Args.cycle(v, 1, specs, 1); assert.strictEqual(v[1], "")
  v = Args.cycle(v, 1, specs, -1); assert.strictEqual(v[1], "sad")
})

test("focus walks text, pills, then back to text", () => {
  assert.strictEqual(Args.stepFocus(-1, 3, 1), 0)
  assert.strictEqual(Args.stepFocus(2, 3, 1), -1)
  assert.strictEqual(Args.stepFocus(-1, 3, -1), 2)
  assert.strictEqual(Args.stepFocus(0, 3, -1), -1)
})

test("display masks passwords and shows placeholders", () => {
  assert.deepStrictEqual(Args.display(specs[2], "abc"), { text: "•••", empty: false })
  assert.deepStrictEqual(Args.display(specs[0], ""), { text: "Name", empty: true })
})

test("missingRequired points at the first empty required pill", () => {
  assert.strictEqual(Args.missingRequired(["a", "", ""], specs), 2)
  assert.strictEqual(Args.missingRequired(["a", "", "b"], specs), -1)
})

test("type filters list All then each type once", () => {
  const cs = [{ typeLabel: "Script" }, { typeLabel: "Application" }, { typeLabel: "Script" }]
  assert.deepStrictEqual(RootSearch.typeFilters(cs).map(f => f.title), ["All", "Application", "Script"])
  assert.strictEqual(RootSearch.filterByType(cs, "Script").length, 2)
  assert.strictEqual(RootSearch.filterByType(cs, "").length, 3)
})

test("a provider's own filters pick candidates by provider and category", () => {
  const cs = [
    { provider: "script-commands", category: "Demo", typeLabel: "Script" },
    { provider: "script-commands", category: "Other", typeLabel: "Script" },
    { provider: "apps", category: "Demo", typeLabel: "Application" }
  ]
  const extra = [{ id: "@script-commands:Demo", title: "Demo" }]
  assert.deepStrictEqual(RootSearch.typeFilters(cs, extra).map(f => f.id), ["", "Application", "Script", "@script-commands:Demo"])
  assert.strictEqual(RootSearch.filterByType(cs, "@script-commands:Demo").length, 1)
})

test("settings provider asks the UI to open the settings window", () => {
  const p = createSettingsProvider()
  assert.deepStrictEqual(p.perform(p.candidates()[0], "open"), { close: true, settings: true, visit: true })
  assert.strictEqual(p.perform(p.candidates()[0], "nope"), undefined)
})

test("every settings field is a real general setting whose options match its default's type", () => {
  const Schema = require("../plugin/core/Schema.js")
  const defaults = Schema.settingsMigrations[0].up({}).general
  for (const f of Schema.generalFields) {
    assert.notStrictEqual(defaults[f.key], undefined, f.key)
    assert.ok(f.options.includes(defaults[f.key]), f.key + " default is one of its options")
    for (const o of f.options) assert.strictEqual(typeof o, typeof defaults[f.key], f.key)
  }
  assert.strictEqual(Schema.generalFields.length, Object.keys(defaults).length)
})

test("answers come first in a query's sections, without a title, and have only their own actions", () => {
  const Ranker = require("../plugin/core/Ranker.js")
  const Frecency = require("../plugin/core/Frecency.js")
  const answer = { id: "calc:answer", title: "4", answer: true }
  const sections = RootSearch.rootSections([], "2+2", { nowMs: 0, answers: q => [answer], fallbacks: () => [] }, { Ranker, Frecency })
  assert.deepStrictEqual(sections.map(s => [s.id, s.title]), [["answers", ""]])
  assert.strictEqual(sections[0].rows[0].candidate, answer)
  assert.deepStrictEqual(RootSearch.actionsFor(answer, [{ id: "copy", title: "Copy" }]).map(a => a.id), ["copy"])
})
