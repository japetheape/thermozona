#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SOURCE_DIR="$REPO_ROOT/custom_components/thermozona"

if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: cannot find $SOURCE_DIR"
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <home-assistant-config-dir>"
  echo "Example: $0 /config"
  exit 1
fi

HA_CONFIG_DIR=$1
TARGET_PARENT="$HA_CONFIG_DIR/custom_components"
TARGET_DIR="$TARGET_PARENT/thermozona"

mkdir -p "$TARGET_PARENT"
rm -rf "$TARGET_DIR"
cp -R "$SOURCE_DIR" "$TARGET_DIR"

echo "Installed Thermozona to: $TARGET_DIR"
echo "Restart Home Assistant to load the updated integration."
