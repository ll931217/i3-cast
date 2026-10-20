pragma Singleton
import QtQuick

QtObject {
  function surfaceSpec(surface, edge, color, width) { return { color: color, width: width } }
}
