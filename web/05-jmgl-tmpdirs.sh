#!/bin/sh
# Create the writable output dir for rendered templates (root filesystem may be read-only).
set -e
mkdir -p /tmp/conf.d
