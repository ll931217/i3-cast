const test = require("node:test")
const assert = require("node:assert/strict")
const Ranker = require("../plugin/core/Ranker.js")
const Frecency = require("../plugin/core/Frecency.js")
const RS = require("../plugin/core/RootSearch.js")
const Apps = require("../plugin/core/AppsProvider.js")
const Web = require("../plugin/core/WebSearchProvider.js")

const deps = { Ranker, Frecency }
const NOW = Date.UTC(2026, 9, 19, 12)

const apps = ["firefox", "chromium", "signal-desktop", "org.gnome.Nautilus", "Alacritty", "libreoffice-writer"].map((id) => ({
  id,
  name: { firefox: "Firefox", chromium: "Chromium", "signal-desktop": "Signal", "org.gnome.Nautilus": "Files", Alacritty: "Alacritty", "libreoffice-writer": "LibreOffice Writer" }[id],
  genericName: { firefox: "Web Browser", chromium: "Web Browser", "org.gnome.Nautilus": "File Manager" }[id] || "",
  keywords: [],
  icon: id
}))

function candidates() {
  return apps.map(Apps.appCandidate)
}

const webSearch = (engines) => Web.createWebSearchProvider({ engines: () => engines || Web.DEFAULT_ENGINES, openUrl() {} })
const fallbacksFor = (engines) => (query) => webSearch(engines).fallbacks(query).map((c) => Object.assign(c, { provider: "web-search", fallback: true }))

function ctx(extra) {
  return Object.assign({ commands: {}, frecency: {}, nowMs: NOW, sensitivity: "medium", fallbacks: fallbacksFor() }, extra || {})
}

const titles = (section) => section.rows.map((r) => r.candidate.title)
const results = (query, c) => RS.rootSections(candidates(), query, c || ctx(), deps)

test("fir finds Firefox first (Phase 1 accept)", () => {
  const sections = results("fir")
  assert.equal(sections[0].id, "results")
  assert.equal(titles(sections[0])[0], "Firefox")
})

test("a query always ends with the fallback section", () => {
  const sections = results("zzzz-nothing")
  assert.equal(sections.length, 1)
  assert.equal(sections[0].id, "fallback-commands")
  assert.equal(sections[0].title, "Use “zzzz-nothing” with…")
  assert.deepEqual(titles(sections[0]), ["Search Google", "Search DuckDuckGo"])
})

test("an exact alias puts its command on top (Phase 1 accept)", () => {
  const c = ctx({ commands: { "app:chromium": { alias: "ff" } } })
  assert.equal(titles(results("ff", c)[0])[0], "Chromium")
  assert.equal(titles(results("f", c)[0])[0], "Chromium", "an alias prefix also wins over title scores")
})

test("launching bumps frecency and teaches the query (Phase 1 accept)", () => {
  // Chromium and Signal tie for "i" on title score alone; a launch decides it.
  const before = titles(results("web")[0])
  assert.deepEqual(before.slice(0, 2), ["Chromium", "Firefox"])
  const visit = Frecency.recordVisit(null, NOW - 1000, "web")
  const c = ctx({ frecency: { "app:firefox": visit } })
  assert.deepEqual(titles(results("web", c)[0]).slice(0, 2), ["Firefox", "Chromium"])
})

test("empty root: favorites, suggestions, applications", () => {
  const c = ctx({
    commands: { "app:firefox": { favoriteOrder: 0 } },
    frecency: { "app:signal-desktop": Frecency.recordVisit(null, NOW - 1000, "") }
  })
  const sections = results("", c)
  assert.deepEqual(sections.map((s) => s.id), ["favorites", "suggestions", "apps"])
  assert.deepEqual(titles(sections[0]), ["Firefox"])
  assert.deepEqual(titles(sections[1]), ["Signal"])
  assert.ok(!titles(sections[2]).includes("Signal"), "suggested apps are not repeated")
})

test("disabled commands are left out", () => {
  const off = results("signal", ctx({ commands: { "app:signal-desktop": { enabled: false } } }))
  assert.ok(!off.some((s) => s.id === "results" && titles(s).includes("Signal")))
})

test("configured fallbacks replace the built-in ones", () => {
  const sections = results("zzzz-nothing", ctx({ fallbacks: fallbacksFor([{ title: "Search Kagi", url: "https://kagi.com/search?q={query}" }]) }))
  assert.deepEqual(titles(sections[0]), ["Search Kagi"])
})

test("actions: primary first, favourites and alias offered", () => {
  const app = RS.decorate(Apps.appCandidate(apps[0]), ctx(), deps)
  const own = Apps.createAppsProvider({ entries: () => [], launch() {}, copyText() {} }).actionsFor(app)
  const ids = RS.actionsFor(app, own).map((a) => a.id)
  assert.equal(ids[0], "open")
  assert.ok(ids.includes("favorite-add") && ids.includes("set-alias") && ids.includes("copy-id"))
})

test("actions without provider-owned entries stay empty rather than promoting generic actions", () => {
  const app = RS.decorate(Apps.appCandidate(apps[0]), ctx({
    commands: { 'app:firefox': { favoriteOrder: 0, alias: 'ff' } },
    frecency: { 'app:firefox': Frecency.recordVisit(null, NOW - 1000, 'firefox') }
  }), deps)
  for (const flags of [{}, { fallback: true }, { answer: true }]) {
    const candidate = Object.assign({}, app, flags)
    assert.deepEqual(RS.actionsFor(candidate, []), [])
    assert.deepEqual(RS.actionsFor(candidate), [])
  }
})

test("favourite reordering", () => {
  const cmds = { a: { favoriteOrder: 0 }, b: { favoriteOrder: 1 }, c: {} }
  assert.deepEqual(RS.reorderFavorites(cmds, "c", "favorite-add"), { a: 0, b: 1, c: 2 })
  assert.deepEqual(RS.reorderFavorites(cmds, "b", "favorite-up"), { b: 0, a: 1 })
  assert.deepEqual(RS.reorderFavorites(cmds, "a", "favorite-remove"), { a: null, b: 0 })
})

test("a query with no provider fallbacks has no fallback section", () => {
  assert.equal(results("zzzz-nothing", ctx({ fallbacks: () => [] })).length, 0)
})

test("fallback URLs encode the query", () => {
  assert.equal(Web.searchUrl(Web.DEFAULT_ENGINES[0], " a&b c "), "https://www.google.com/search?q=a%26b%20c")
})
