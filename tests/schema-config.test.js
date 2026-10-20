const test = require("node:test")
const assert = require("node:assert/strict")
const Schema = require("../plugin/core/Schema.js")

test("config defaults apply when nothing is configured", () => {
  const c = Schema.withConfigDefaults(null)
  assert.equal(c.logLevel, "info")
  assert.equal(c.keepVisibleOnFocusLoss, false)
  assert.deepEqual(c.general, {})
  assert.equal(c.fallbacks, null)
})

test("general overrides keep only known keys of the right type and enum value", () => {
  const c = Schema.withConfigDefaults({
    general: { windowMode: "compact", uiZoom: 1.25, popToRootTimeout: "soon", escapeKeyBehavior: "explode", nonsense: 1 }
  })
  assert.deepEqual(c.general, { windowMode: "compact", uiZoom: 1.25 })
})

test("fallbacks need a title and a {query} url", () => {
  const list = Schema.validFallbacks([
    { title: "Kagi", url: "https://kagi.com/search?q={query}" },
    { title: "No placeholder", url: "https://example.com" },
    { url: "https://x/{query}" }
  ])
  assert.equal(list.length, 1)
  assert.equal(list[0].id, "fallback:0")
  assert.equal(Schema.validFallbacks([]), null)
})
