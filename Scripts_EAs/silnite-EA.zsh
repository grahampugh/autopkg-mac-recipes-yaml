#!/bin/zsh
# shellcheck shell=bash

# Get the silnite version from file

# variables
silnite_dir="/Library/Application Support/ETHZ/silnite"
silnite_version_file="$silnite_dir/silnite-version.txt"

version=""
if [[ -f "$silnite_version_file" ]]; then
    version=$(/bin/cat "$silnite_version_file")
fi

result="None"

if [[ $version ]]; then
    result="$version"
fi

echo "<result>$result</result>"

exit 0