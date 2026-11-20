#!/usr/bin/env bash

DEVICE="intel_backlight"

case "$1" in
    max|100)
        if command -v brightnessctl >/dev/null 2>&1; then
            brightnessctl set 100%
        else
            MAX=$(cat /sys/class/backlight/"$DEVICE"/max_brightness 2>/dev/null || echo 4882)
            busctl call org.freedesktop.login1 /org/freedesktop/login1/session/auto org.freedesktop.login1.Session SetBrightness ssu backlight "$DEVICE" "$MAX"
        fi
        ;;
    min|0)
        if command -v brightnessctl >/dev/null 2>&1; then
            brightnessctl set 0%
        else
            busctl call org.freedesktop.login1 /org/freedesktop/login1/session/auto org.freedesktop.login1.Session SetBrightness ssu backlight "$DEVICE" 0
        fi
        ;;
    *)
        echo "Usage: $0 {max|min}"
        exit 1
        ;;
esac
