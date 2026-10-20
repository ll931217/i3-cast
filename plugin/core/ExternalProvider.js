// Provider adapter for plugins that live outside the JS runtime (the Python host).
// `bridge` is a set of functions that return JSON strings:
//   candidates(id), fallbacks(id, query), actionsFor(id, candidateJson), perform(id, candidateJson, action, ctxJson)
// `info` is {id, hasFallbacks}.

function createExternalProvider(bridge, info) {
  var provider = {
    id: info.id,

    candidates: function() { return JSON.parse(bridge.candidates(info.id)) },

    actionsFor: function(candidate) {
      return JSON.parse(bridge.actionsFor(info.id, JSON.stringify(candidate)))
    },

    perform: function(candidate, actionId, ctx) {
      var raw = bridge.perform(info.id, JSON.stringify(candidate), actionId, JSON.stringify(ctx || {}))
      var outcome = JSON.parse(raw)
      return outcome === null ? undefined : outcome
    }
  }
  if (info.hasFallbacks) provider.fallbacks = function(query) { return JSON.parse(bridge.fallbacks(info.id, query)) }
  return provider
}

if (typeof module !== "undefined") module.exports = { createExternalProvider: createExternalProvider }
