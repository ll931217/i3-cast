const test = require("node:test")
const assert = require("node:assert")
const { createExternalProvider } = require("../plugin/core/ExternalProvider.js")

const bridge = {
  candidates: id => JSON.stringify([{ id: id + ":a" }]),
  fallbacks: (id, q) => JSON.stringify([{ id: "f", subtitle: q }]),
  actionsFor: (id, c) => JSON.stringify([{ id: "run", title: "Run " + JSON.parse(c).id }]),
  perform: (id, c, action, ctx) => JSON.stringify(action === "run" ? { close: true, args: JSON.parse(ctx).arguments } : null)
}

test("wraps the JSON bridge as a provider", () => {
  const p = createExternalProvider(bridge, { id: "x", hasFallbacks: true })
  assert.deepStrictEqual(p.candidates(), [{ id: "x:a" }])
  assert.strictEqual(p.actionsFor({ id: "x:a" })[0].title, "Run x:a")
  assert.deepStrictEqual(p.perform({ id: "x:a" }, "run", { arguments: ["Ann"] }), { close: true, args: ["Ann"] })
  assert.strictEqual(p.perform({ id: "x:a" }, "other", {}), undefined)
  assert.strictEqual(p.fallbacks("q")[0].subtitle, "q")
})

test("no fallbacks function when the plugin has none", () => {
  assert.strictEqual(createExternalProvider(bridge, { id: "x", hasFallbacks: false }).fallbacks, undefined)
})
