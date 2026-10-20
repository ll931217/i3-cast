const test = require("node:test")
const assert = require("node:assert/strict")
const P = require("../plugin/core/Providers.js")
const Apps = require("../plugin/core/AppsProvider.js")
const Web = require("../plugin/core/WebSearchProvider.js")

const toy = (id, rows, extra) => Object.assign({
  id,
  candidates: () => rows.map((title) => ({ id: id + ":" + title, title })),
  actionsFor: () => [{ id: "open", title: "Open " + id }],
  perform: (c, action) => (action === "open" ? { close: true, visit: true } : undefined)
}, extra || {})

test("candidates are tagged with their provider, in registration order", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("one", ["a", "b"]))
  P.register(reg, toy("two", ["c"]))
  assert.deepEqual(P.candidates(reg).map((c) => [c.id, c.provider]), [["one:a", "one"], ["one:b", "one"], ["two:c", "two"]])
})

test("registering rejects bad ids, duplicates and missing methods", () => {
  const reg = P.createRegistry()
  assert.throws(() => P.register(reg, toy("Bad Id", [])), /Invalid provider id/)
  assert.throws(() => P.register(reg, { id: "half", candidates() {} }), /lacks actionsFor/)
  P.register(reg, toy("dup", []))
  assert.throws(() => P.register(reg, toy("dup", [])), /already registered/)
})

test("a provider that throws is skipped and recorded, the others still answer", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("broken", [], { candidates: () => { throw new Error("boom") } }))
  P.register(reg, toy("fine", ["x"]))
  assert.deepEqual(P.candidates(reg).map((c) => c.id), ["fine:x"])
  assert.equal(reg.errors[0].provider, "broken")
  assert.match(reg.errors[0].error, /boom/)
})

test("unregister removes a provider's rows", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("one", ["a"]))
  P.unregister(reg, "one")
  assert.deepEqual(P.candidates(reg), [])
})

test("perform and actionsFor dispatch on candidate.provider", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("one", ["a"]))
  const [c] = P.candidates(reg)
  assert.deepEqual(P.actionsFor(reg, c).map((a) => a.title), ["Open one"])
  assert.deepEqual(P.perform(reg, c, "open", {}), { close: true, visit: true })
  assert.equal(P.perform(reg, c, "unknown", {}), undefined)
})

test("apps provider launches and copies through injected services", () => {
  const calls = []
  const reg = P.createRegistry()
  P.register(reg, Apps.createAppsProvider({
    entries: () => [{ id: "firefox", name: "Firefox", icon: "firefox" }, { name: "no id" }],
    launch: (id, title) => calls.push(["launch", id, title]),
    copyText: (t) => calls.push(["copy", t])
  }))
  const cands = P.candidates(reg)
  assert.deepEqual(cands.map((c) => c.id), ["app:firefox"])
  assert.deepEqual(P.perform(reg, cands[0], "open", {}), { close: true, visit: true })
  assert.equal(P.perform(reg, cands[0], "copy-id", {}).hud, "Copied to Clipboard")
  assert.deepEqual(calls, [["launch", "firefox", "Firefox"], ["copy", "firefox.desktop"]])
})

test("web search offers fallbacks only, and opens the encoded url", () => {
  const opened = []
  const reg = P.createRegistry()
  P.register(reg, Web.createWebSearchProvider({ engines: () => Web.DEFAULT_ENGINES, openUrl: (u) => opened.push(u) }))
  assert.deepEqual(P.candidates(reg), [])
  const rows = P.fallbacks(reg, "a b")
  assert.deepEqual(rows.map((r) => r.title), ["Search Google", "Search DuckDuckGo"])
  assert.ok(rows.every((r) => r.fallback && r.provider === "web-search"))
  assert.equal(P.findFallback(reg, "fallback:1").title, "Search DuckDuckGo")
  P.perform(reg, rows[0], "open", { query: "a b" })
  assert.deepEqual(opened, ["https://www.google.com/search?q=a%20b"])
})

test("filters() collects provider dropdown entries and skips a throwing provider", () => {
  const P = require("../plugin/core/Providers.js")
  const reg = P.createRegistry()
  const base = { candidates: () => [], actionsFor: () => [], perform: () => undefined }
  P.register(reg, Object.assign({ id: "a", filters: () => [{ id: "x", title: "X" }] }, base))
  P.register(reg, Object.assign({ id: "b", filters: () => { throw new Error("no") } }, base))
  P.register(reg, Object.assign({ id: "c" }, base))
  assert.deepStrictEqual(P.filters(reg), [{ id: "@a:x", title: "X", provider: "a" }])
  assert.strictEqual(reg.errors.length, 1)
})

test("answers() tags rows, and findAnswer resolves them for the same query", () => {
  const reg = P.createRegistry()
  P.register(reg, { id: "calc", candidates: () => [], actionsFor: () => [], perform: () => undefined,
    answers: q => q === "2+2" ? [{ id: "calc:answer", title: "4" }] : [] })
  const rows = P.answers(reg, "2+2")
  assert.strictEqual(rows[0].answer, true)
  assert.strictEqual(rows[0].provider, "calc")
  assert.deepStrictEqual(P.answers(reg, "firefox"), [])
  assert.strictEqual(P.findAnswer(reg, "calc:answer", "2+2").title, "4")
  assert.strictEqual(P.findAnswer(reg, "calc:answer", "firefox"), null)
})
