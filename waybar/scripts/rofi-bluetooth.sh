#!/usr/bin/env bash

# Logging for instant diagnostics
LOG_FILE="/tmp/rofi-bluetooth.log"
exec >> "$LOG_FILE" 2>&1
echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] rofi-bluetooth.sh triggered (PID: $$) ==="

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
THEME="$DIR/rofi-bluetooth.rasi"
PID_FILE="/tmp/rofi-bluetooth.pid"

# Toggle behavior: if an instance of this bluetooth menu is currently running elsewhere, close it
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && [ "$OLD_PID" != "$$" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Active external menu instance found with PID $OLD_PID. Toggling off..."
        kill "$OLD_PID" 2>/dev/null
        rm -f "$PID_FILE"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# Store our PID and clean up on exit
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT INT TERM

# Check if bluetooth controller is powered on
power_status=""
if command -v rfkill >/dev/null 2>&1; then
    if rfkill list bluetooth 2>/dev/null | grep -qi "Soft blocked: yes"; then
        power_status="no"
    fi
fi

if [ -z "$power_status" ] && command -v bluetoothctl >/dev/null 2>&1; then
    power_status=$(timeout 2 bluetoothctl show 2>/dev/null | awk '/Powered:/ {print tolower($2)}')
fi

# Fallback: assume yes so menu opens instead of failing silently
if [ -z "$power_status" ]; then
    power_status="yes"
fi

echo "Power status: $power_status"

# If bluetooth is turned off, provide an easy toggle option
if [ "$power_status" != "yes" ]; then
    chosen=$(printf "󰂯  Turn Bluetooth On\n󰒓  Open Bluetooth Manager" | rofi -dmenu -p "󰂲 Bluetooth" -theme "$THEME")
    echo "Bluetooth off selection: '$chosen'"
    case "$chosen" in
        "󰂯  Turn Bluetooth On"*)
            rfkill unblock bluetooth 2>/dev/null
            timeout 2 bluetoothctl power on >/dev/null 2>&1
            notify-send "Bluetooth" "Bluetooth turned on" -i bluetooth-active 2>/dev/null
            rm -f "$PID_FILE"
            exec "$0"
            ;;
        "󰒓  Open Bluetooth Manager"*)
            blueman-manager >/dev/null 2>&1 &
            ;;
    esac
    exit 0
fi

# Collect connected device MACs
connected_macs=$(timeout 2 bluetoothctl devices Connected 2>/dev/null | awk '{print $2}')

# Query all available devices with a safety timeout
devices_output=$(timeout 2 bluetoothctl devices 2>/dev/null)
menu_items=""

if [ -n "$devices_output" ]; then
    while read -r _ mac name; do
        [ -z "$mac" ] && continue
        [ -z "$name" ] && name="Unknown Device"
        
        # Truncate device name cleanly if long
        clean_name="${name:0:22}"
        
        if echo "$connected_macs" | grep -qi "$mac"; then
            label=$(printf "󰂱  %-22s  [ Disconnect ]    %s" "$clean_name" "$mac")
        else
            label=$(printf "󰂯  %-22s  [ Connect ]       %s" "$clean_name" "$mac")
        fi
        
        if [ -z "$menu_items" ]; then
            menu_items="$label"
        else
            menu_items="${menu_items}\n${label}"
        fi
    done <<< "$devices_output"
fi

# Action buttons
actions="󰑐  Scan for Nearby Devices\n󰂲  Turn Bluetooth Off\n󰒓  Open Bluetooth Manager"

if [ -n "$menu_items" ]; then
    menu_items="${menu_items}\n────────────────────────────────────────────\n${actions}"
else
    menu_items="󰂯  No Devices Found (Click to Scan)\n────────────────────────────────────────────\n${actions}"
fi

# Display menu in rofi
chosen=$(echo -e "$menu_items" | rofi -dmenu -p "󰂯 Bluetooth" -theme "$THEME")
echo "Selected: '$chosen'"

[ -z "$chosen" ] && exit 0

case "$chosen" in
    "────────────────────────────────────────────")
        exit 0
        ;;
    "󰑐  Scan for Nearby Devices"*|"󰂯  No Devices Found (Click to Scan)"*)
        notify-send "Bluetooth" "Scanning for nearby devices (5s)..." -i bluetooth-active 2>/dev/null
        timeout 5 bluetoothctl scan on >/dev/null 2>&1
        rm -f "$PID_FILE"
        exec "$0"
        ;;
    "󰂲  Turn Bluetooth Off"*)
        timeout 2 bluetoothctl power off >/dev/null 2>&1
        notify-send "Bluetooth" "Bluetooth turned off" -i bluetooth-disabled 2>/dev/null
        ;;
    "󰒓  Open Bluetooth Manager"*)
        blueman-manager >/dev/null 2>&1 &
        ;;
    *)
        # Extract MAC address using regex from the selected line
        mac=$(echo "$chosen" | grep -o -E '([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}')
        
        if [ -n "$mac" ]; then
            # Query clean device alias/name from bluetoothctl
            dev_name=$(timeout 2 bluetoothctl info "$mac" 2>/dev/null | awk -F': ' '/Alias:/ {print $2}')
            [ -z "$dev_name" ] && dev_name="$mac"
            
            if echo "$chosen" | grep -qi "Disconnect"; then
                notify-send "Bluetooth" "Disconnecting from $dev_name..." -i bluetooth-active 2>/dev/null
                timeout 5 bluetoothctl disconnect "$mac" >/dev/null 2>&1
                notify-send "Bluetooth" "Disconnected from $dev_name" -i bluetooth-active 2>/dev/null
            else
                notify-send "Bluetooth" "Connecting to $dev_name..." -i bluetooth-active 2>/dev/null
                # Check if device is already paired
                if timeout 2 bluetoothctl info "$mac" 2>/dev/null | grep -qi "Paired: yes"; then
                    echo "Device $mac is already paired. Connecting..."
                else
                    echo "Device $mac not paired yet. Pairing..."
                    timeout 6 bluetoothctl pair "$mac" >/dev/null 2>&1
                fi
                timeout 5 bluetoothctl trust "$mac" >/dev/null 2>&1
                if timeout 8 bluetoothctl connect "$mac" >/dev/null 2>&1; then
                    notify-send "Bluetooth" "Connected to $dev_name" -i bluetooth-active 2>/dev/null
                else
                    notify-send "Bluetooth" "Failed to connect to $dev_name" -u critical -i bluetooth-disabled 2>/dev/null
                fi
            fi
            
            # Reopen menu to reflect updated connection state
            rm -f "$PID_FILE"
            exec "$0"
        fi
        ;;
esac
