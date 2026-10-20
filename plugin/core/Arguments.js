// Inline argument pills (SPEC §10.1): a command with `arguments` shows one pill per argument
// after the search text. `specs` is [{placeholder, type: text|password|dropdown, optional, data}].
// Focus is -1 for the search text, else the pill index. Values are an array of strings.

function initialValues(specs) {
  return (specs || []).map(function() { return "" })
}

function setValue(values, index, value) {
  var out = values.slice()
  out[index] = value
  return out
}

function typeText(values, index, specs, text) {
  if (!specs[index] || specs[index].type === "dropdown") return values
  return setValue(values, index, values[index] + text)
}

function backspace(values, index) {
  return setValue(values, index, values[index].slice(0, -1))
}

// Dropdowns step through their options; an optional one also has "no value" before the first.
function cycle(values, index, specs, direction) {
  var spec = specs[index]
  if (!spec || spec.type !== "dropdown") return values
  var options = (spec.optional ? [""] : []).concat(spec.data || [])
  if (options.length === 0) return values
  var at = options.indexOf(values[index])
  var next = (at + direction + options.length) % options.length
  return setValue(values, index, options[next])
}

// Tab (+1) and Shift+Tab (-1) walk search text -> pill 0 -> ... -> back to search text.
function stepFocus(focus, count, direction) {
  var next = focus + direction
  if (next >= count) return -1
  if (next < -1) return count - 1
  return next
}

// What a pill shows: its value (masked for passwords), else the placeholder.
function display(spec, value) {
  if (!value) return { text: spec.placeholder || "", empty: true }
  return { text: spec.type === "password" ? new Array(value.length + 1).join("•") : value, empty: false }
}

function missingRequired(values, specs) {
  for (var i = 0; i < specs.length; i++) if (!specs[i].optional && !values[i]) return i
  return -1
}

if (typeof module !== "undefined") {
  module.exports = {
    initialValues: initialValues, setValue: setValue, typeText: typeText, backspace: backspace,
    cycle: cycle, stepFocus: stepFocus, display: display, missingRequired: missingRequired
  }
}
