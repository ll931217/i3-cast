// Import-free execution boundary, wired by QML and also usable from node.
function create(deps) {
  var pending = Object.create(null)
  var sequence = 0
  // JSON.stringify alone silently loses undefined/functions and turns NaN into null.
  // Validate first, including unknown fields, before copying across the boundary.
  function copy(value, ancestors) {
    if (value === null || typeof value === "string" || typeof value === "boolean") return value
    if (typeof value === "number" && isFinite(value)) return value
    if (typeof value !== "object" || value === null) throw new Error("Expected JSON data")
    ancestors = ancestors || []
    if (ancestors.indexOf(value) !== -1) throw new Error("Cyclic JSON data")
    var array = Array.isArray(value)
    var proto = Object.getPrototypeOf(value)
    if (!array && proto !== Object.prototype && proto !== null) throw new Error("Expected JSON object")
    if (Object.getOwnPropertySymbols(value).length) throw new Error("Expected JSON keys")
    var stack = ancestors.concat([value])
    var result = array ? [] : {}
    var keys = Object.keys(value)
    if (array && keys.length !== value.length) throw new Error("Expected dense JSON array")
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i]
      if (array && key !== String(i)) throw new Error("Expected JSON array indices")
      var descriptor = Object.getOwnPropertyDescriptor(value, key)
      if (!Object.prototype.hasOwnProperty.call(descriptor, "value")) throw new Error("Expected JSON value")
      Object.defineProperty(result, key, { value: copy(descriptor.value, stack), enumerable: true, writable: true, configurable: true })
    }
    return result
  }
  function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value) }
  function has(value, key) { return Object.prototype.hasOwnProperty.call(value, key) }
  function validateOutcome(value) {
    var outcome = copy(value)
    if (!object(outcome)) throw new Error("Expected outcome object")
    var booleans = ["close", "visit", "settings"]
    for (var i = 0; i < booleans.length; i++) {
      var key = booleans[i]
      if (has(outcome, key) && typeof outcome[key] !== "boolean") throw new Error("Expected outcome boolean: " + key)
    }
    if (has(outcome, "hud") && typeof outcome.hud !== "string") throw new Error("Expected HUD text")
    if (has(outcome, "push") && !object(outcome.push)) throw new Error("Expected navigation object")
    if (has(outcome, "prompt")) {
      var p = outcome.prompt
      if (!object(p) || (p.kind !== "arguments" && p.kind !== "confirmation")
          || (has(p, "title") && typeof p.title !== "string") || has(outcome, "close") || has(outcome, "visit")) {
        throw new Error("Invalid prompt outcome")
      }
    }
    if (has(outcome, "toast")) {
      var toast = outcome.toast
      if (!object(toast) || (toast.style !== "success" && toast.style !== "failure") || typeof toast.title !== "string") {
        throw new Error("Invalid toast")
      }
      if (has(toast, "actions")) {
        if (!Array.isArray(toast.actions)) throw new Error("Expected toast actions")
        for (var j = 0; j < toast.actions.length; j++) {
          var a = toast.actions[j]
          if (!object(a) || typeof a.title !== "string" || (!has(a, "copy") && !has(a, "open"))
              || (has(a, "copy") && typeof a.copy !== "string") || (has(a, "open") && typeof a.open !== "string")) {
            throw new Error("Invalid toast action")
          }
        }
      }
    }
    return outcome
  }
  function validateTarget(target) {
    if (!object(target) || has(target, "ref") === has(target, "id")) throw new Error("Expected target ref or id")
    var key = has(target, "ref") ? "ref" : "id"
    if (target[key] === null || target[key] === undefined || target[key] === "") throw new Error("Invalid target")
  }
  function resolve(target) {
    validateTarget(target)
    var result = deps.resolve(copy(target))
    if (!result || !result.candidate) throw new Error("Unknown target")
    return copy(result)
  }
  function actions(target) {
    return copy(deps.actions(copy(resolve(target).candidate)))
  }
  function prompt(state, value, outcome) {
    if (Object.keys(pending).length >= 128) throw new Error("Too many pending prompts; cancel unused prompts")
    var token = "execution-" + (++sequence)
    state.prompt = value.kind
    pending[token] = state
    var result = copy(outcome || { prompt: value })
    result.continuation = token
    result.target = copy(state.target)
    result.candidate = copy(state.candidate)
    result.arguments = copy(state.args)
    return result
  }
  function execute(request) {
    var state
    if (request.continuation !== undefined) {
      if (typeof request.continuation !== "string") throw new Error("Invalid continuation")
      state = pending[request.continuation]
      if (!state) throw new Error("Invalid continuation")
      // Consume before validation, resolution or dispatch: even failures cannot replay.
      delete pending[request.continuation]
      validateTarget(request.target)
      var targetKey = has(state.target, "ref") ? "ref" : "id"
      if (!has(request.target, targetKey) || JSON.stringify(request.target[targetKey]) !== JSON.stringify(state.target[targetKey])) {
        throw new Error("Continuation target mismatch")
      }
      var live = resolve(state.target)
      if (live.candidate.id !== state.candidate.id || live.candidate.provider !== state.candidate.provider
          || (typeof deps.identity === "function" && deps.identity(live.candidate) !== state.identity)) {
        throw new Error("Continuation candidate/provider identity changed")
      }
    } else {
      var resolved = resolve(request.target)
      var action = request.action
      if (!action) {
        var list = deps.actions(copy(resolved.candidate))
        if (!list.length) throw new Error("No primary action")
        action = list[0].id
      }
      state = { candidate: resolved.candidate, query: resolved.query, target: copy(request.target), action: action, explicit: !!request.action, args: [] }
      state.identity = typeof deps.identity === "function" ? deps.identity(resolved.candidate) : null
    }
    if (request.action !== undefined && typeof request.action !== "string") throw new Error("Expected action string")
    var args = copy(request.arguments === undefined ? [] : request.arguments)
    if (!Array.isArray(args) || args.some(function(value) { return typeof value !== "string" })) throw new Error("Expected argument strings")
    if (typeof state.action !== "string" || !state.action) throw new Error("Invalid provider action")
    var confirmed = state.prompt === "confirmation" && JSON.stringify(args) === JSON.stringify(state.args)
      && (!request.action || request.action === state.action)
    if (request.action) { state.action = request.action; state.explicit = true }
    state.args = args
    // The parent identifies RootSearch-generated actions; providers still get
    // first refusal below, but these actions do not need script arguments.
    var isGeneric = typeof deps.isGeneric === "function" && deps.isGeneric(state.action)
    var specs = isGeneric ? [] : (state.candidate.arguments || [])
    for (var i = 0; i < specs.length; i++) {
      if (!specs[i].optional && !args[i]) return prompt(state, { kind: "arguments", title: state.candidate.title || "Arguments" })
    }
    // Everything after invoking perform is potentially side-effecting. Never retry,
    // including on malformed results or errors from generic dispatch/visit.
    var candidate = copy(state.candidate)
    var ctx = { query: state.query, arguments: copy(args), confirmed: confirmed }
    try {
      var outcome = deps.perform(candidate, state.action, ctx)
      if (outcome === undefined) {
        if (!state.explicit) throw new Error("Provider did not handle primary action")
        outcome = deps.generic(copy(state.candidate), state.action)
      }
      outcome = validateOutcome(outcome)
      if (outcome.prompt) return prompt(state, outcome.prompt, outcome)
      if (outcome.visit) deps.visit(state.candidate.id, state.query)
      delete outcome.visit
      return outcome
    } catch (error) {
      throw new Error(String(error && error.message || error) + "; side effects may already have occurred")
    }
  }
  function cancel(token) { delete pending[token] }
  function clear() { pending = Object.create(null) }
  return { actions: actions, execute: execute, cancel: cancel, clear: clear }
}

if (typeof module !== "undefined") module.exports = { create: create }
