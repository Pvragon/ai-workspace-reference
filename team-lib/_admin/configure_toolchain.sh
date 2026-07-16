#!/usr/bin/env bash
#
# configure_toolchain.sh
# Declarative toolchain provisioning for the Pvragon AI Workspace.
# Reads toolchain.yaml and installs CLI tools + configures MCP servers.
#
# Flags:
#   --client <name>   Skip interactive, configure one client
#   --cli-only        Only install CLI tools, skip MCP
#   --mcp-only        Only configure MCP, skip CLI tools
#   --dry-run         Show what would change without modifying anything
#   --update-only     Non-interactive, read state file, install new tools/servers only
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN_YAML="$SCRIPT_DIR/toolchain.yaml"
PARSE_SCRIPT="$SCRIPT_DIR/parse_toolchain.py"
STATE_FILE="$HOME/.pvragon-toolchain-state.json"

# Client registry: client_key -> config_path:json_key
declare -A CLIENT_CONFIGS=(
    [claude]="$HOME/.claude.json:mcpServers"
    [gemini]="$HOME/.gemini/antigravity/mcp_config.json:mcpServers"
)

declare -A CLIENT_LABELS=(
    [claude]="Claude Code"
    [gemini]="Gemini CLI"
)

# Parse flags
DRY_RUN=false
CLI_ONLY=false
MCP_ONLY=false
UPDATE_ONLY=false
SELECTED_CLIENT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true; shift ;;
        --cli-only)   CLI_ONLY=true; shift ;;
        --mcp-only)   MCP_ONLY=true; shift ;;
        --update-only) UPDATE_ONLY=true; shift ;;
        --client)     SELECTED_CLIENT="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

# ============================================================================
# PREREQUISITES
# ============================================================================

if [[ ! -f "$TOOLCHAIN_YAML" ]]; then
    echo "    ⚠️  toolchain.yaml not found at $TOOLCHAIN_YAML. Skipping."
    exit 0
fi

if ! command -v jq &>/dev/null; then
    echo "    ❌ jq is required but not installed. Run: sudo apt install jq"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "    ❌ python3 is required but not installed."
    exit 1
fi

# Parse YAML to JSON
TOOLCHAIN_JSON=$(python3 "$PARSE_SCRIPT" "$TOOLCHAIN_YAML")

# ============================================================================
# CLI TOOL INSTALLATION
# ============================================================================

# Global npm installs need root when node comes from apt (/usr prefix), which
# breaks every npm-type tool for a normal user. Redirect the global prefix to
# a user-level directory once, so the toolchain never needs sudo.
NPM_PREFIX_READY=false
ensure_npm_user_prefix() {
    [[ "$NPM_PREFIX_READY" == "true" ]] && return 0
    NPM_PREFIX_READY=true
    if [[ $EUID -ne 0 ]]; then
        local prefix
        prefix=$(npm config get prefix 2>/dev/null || echo /usr)
        if [[ "$prefix" == /usr* && ! -w "$prefix/lib/node_modules" ]]; then
            npm config set prefix "$HOME/.npm-global"
            mkdir -p "$HOME/.npm-global/bin"
            export PATH="$HOME/.npm-global/bin:$PATH"
            if ! grep -q '.npm-global/bin' "$HOME/.bashrc" 2>/dev/null; then
                echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> "$HOME/.bashrc"
            fi
            echo "    ℹ️  npm global prefix set to ~/.npm-global (user-writable, no sudo)"
        fi
    fi
}

install_cli_tools() {
    echo ""
    echo "---> CLI Tools"

    local tools
    tools=$(echo "$TOOLCHAIN_JSON" | jq -r '.cli_tools | keys[]')

    local post_notes=()

    for tool in $tools; do
        local desc check_cmd install_type install_cmd notes
        desc=$(echo "$TOOLCHAIN_JSON" | jq -r ".cli_tools.\"$tool\".description")
        check_cmd=$(echo "$TOOLCHAIN_JSON" | jq -r ".cli_tools.\"$tool\".check_command")
        install_type=$(echo "$TOOLCHAIN_JSON" | jq -r ".cli_tools.\"$tool\".install_type")
        install_cmd=$(echo "$TOOLCHAIN_JSON" | jq -r ".cli_tools.\"$tool\".install_command")
        notes=$(echo "$TOOLCHAIN_JSON" | jq -r ".cli_tools.\"$tool\".post_install_notes // empty")

        printf "    %-40s" "$tool ($desc)..."

        if eval "$check_cmd" &>/dev/null; then
            local version
            version=$(eval "$check_cmd" 2>/dev/null | head -1)
            echo "✅ already installed ($version)"
        else
            if [[ "$DRY_RUN" == "true" ]]; then
                echo "🔍 would install ($install_type: $install_cmd)"
            elif [[ "$install_type" == "apt" ]]; then
                echo "⚠️  not installed (requires sudo: $install_cmd)"
            elif [[ "$install_type" == "npm" ]]; then
                ensure_npm_user_prefix
                echo -n "installing..."
                if eval "$install_cmd" &>/dev/null; then
                    echo " ✅ installed"
                else
                    echo " ❌ install failed (retry by hand: $install_cmd — check network and 'npm config get prefix')"
                fi
            else
                echo "⚠️  unknown install_type: $install_type"
            fi
        fi

        if [[ -n "$notes" ]]; then
            post_notes+=("$tool: $notes")
        fi
    done

    # Print post-install notes
    if [[ ${#post_notes[@]} -gt 0 ]]; then
        echo ""
        echo "    ℹ️  Notes:"
        for note in "${post_notes[@]}"; do
            echo "    - $note"
        done
    fi
}

# ============================================================================
# MCP SERVER CONFIGURATION
# ============================================================================

merge_mcp_server() {
    local config_path="$1"
    local json_key="$2"
    local server_name="$3"
    local server_config="$4"

    # Check if server already exists
    if [[ -f "$config_path" ]] && jq -e ".${json_key}.\"${server_name}\"" "$config_path" &>/dev/null; then
        printf "      %-24s" "$server_name"
        echo "✅ already configured"
        return 0
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        printf "      %-24s" "$server_name"
        echo "🔍 would add"
        return 0
    fi

    # Ensure config file exists with base structure
    if [[ ! -f "$config_path" ]]; then
        local config_dir
        config_dir=$(dirname "$config_path")
        mkdir -p "$config_dir"
        echo "{\"${json_key}\":{}}" > "$config_path"
    fi

    # Backup before modification
    cp "$config_path" "${config_path}.toolchain-backup"

    # Merge using jq
    local new_json
    new_json=$(jq --argjson server "$server_config" \
        ".${json_key}.\"${server_name}\" = \$server" \
        "$config_path")

    # Validate the resulting JSON
    if echo "$new_json" | jq '.' &>/dev/null; then
        echo "$new_json" > "$config_path"
        printf "      %-24s" "$server_name"
        echo "✅ added"
    else
        # Restore backup on failure
        cp "${config_path}.toolchain-backup" "$config_path"
        printf "      %-24s" "$server_name"
        echo "❌ JSON validation failed, restored backup"
        return 1
    fi
}

configure_mcp_for_client() {
    local client="$1"
    local config_entry="${CLIENT_CONFIGS[$client]}"
    local config_path="${config_entry%%:*}"
    local json_key="${config_entry##*:}"
    local label="${CLIENT_LABELS[$client]}"

    echo ""
    echo "    Configuring $label..."

    local servers
    servers=$(echo "$TOOLCHAIN_JSON" | jq -r '.mcp_servers | keys[]')

    local post_notes=()

    for server in $servers; do
        local server_config notes
        server_config=$(echo "$TOOLCHAIN_JSON" | jq ".mcp_servers.\"$server\".config.\"$client\" // empty")
        notes=$(echo "$TOOLCHAIN_JSON" | jq -r ".mcp_servers.\"$server\".post_install_notes // empty")

        if [[ -z "$server_config" || "$server_config" == "null" ]]; then
            printf "      %-24s" "$server"
            echo "⚠️  no config for $client"
        else
            merge_mcp_server "$config_path" "$json_key" "$server" "$server_config"
        fi

        if [[ -n "$notes" ]]; then
            post_notes+=("$server: $notes")
        fi
    done

    # Print post-install notes
    if [[ ${#post_notes[@]} -gt 0 ]]; then
        echo ""
        echo "    ⚠️  Post-setup reminders:"
        for note in "${post_notes[@]}"; do
            echo "    - $note"
        done
    fi
}

select_clients_interactive() {
    echo ""
    echo "---> MCP Server Configuration"
    echo "    Which AI clients do you use? (space-separated numbers, or 'all')"

    local i=1
    # Fixed order to ensure stable menu numbering
    local client_list=(claude gemini)
    for client in "${client_list[@]}"; do
        echo "      $i) ${CLIENT_LABELS[$client]}"
        ((i++))
    done
    echo "      s) Skip MCP setup"
    echo ""

    read -p "    Select: " selection

    if [[ "$selection" == "s" || "$selection" == "S" ]]; then
        return 1
    fi

    local selected_clients=()

    if [[ "$selection" == "all" ]]; then
        selected_clients=("${client_list[@]}")
    else
        for num in $selection; do
            local idx=$((num - 1))
            if [[ $idx -ge 0 && $idx -lt ${#client_list[@]} ]]; then
                selected_clients+=("${client_list[$idx]}")
            fi
        done
    fi

    if [[ ${#selected_clients[@]} -eq 0 ]]; then
        echo "    No valid selection. Skipping MCP setup."
        return 1
    fi

    # Save state
    save_state "${selected_clients[@]}"

    for client in "${selected_clients[@]}"; do
        configure_mcp_for_client "$client"
    done
}

# ============================================================================
# STATE FILE
# ============================================================================

save_state() {
    local clients=("$@")
    local clients_json
    clients_json=$(printf '%s\n' "${clients[@]}" | jq -R . | jq -s .)

    jq -n \
        --argjson clients "$clients_json" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{selected_clients: $clients, last_configured: $ts}' \
        > "$STATE_FILE"
}

load_state() {
    if [[ -f "$STATE_FILE" ]]; then
        jq -r '.selected_clients[]' "$STATE_FILE"
    fi
}

# ============================================================================
# MAIN
# ============================================================================

echo ""
echo "=== Team Toolchain Setup ==="

# CLI tools
if [[ "$MCP_ONLY" != "true" ]]; then
    install_cli_tools
fi

# MCP servers
if [[ "$CLI_ONLY" != "true" ]]; then
    if [[ -n "$SELECTED_CLIENT" ]]; then
        # Direct client selection via flag
        if [[ -n "${CLIENT_CONFIGS[$SELECTED_CLIENT]+x}" ]]; then
            configure_mcp_for_client "$SELECTED_CLIENT"
            save_state "$SELECTED_CLIENT"
        else
            echo "    ❌ Unknown client: $SELECTED_CLIENT"
            echo "    Available: ${!CLIENT_CONFIGS[*]}"
            exit 1
        fi
    elif [[ "$UPDATE_ONLY" == "true" ]]; then
        # Non-interactive: use saved state
        local_clients=$(load_state)
        if [[ -n "$local_clients" ]]; then
            echo ""
            echo "---> MCP Server Configuration (update mode)"
            while IFS= read -r client; do
                configure_mcp_for_client "$client"
            done <<< "$local_clients"
        else
            echo "    ℹ️  No saved client preferences. Run setup to configure MCP servers."
        fi
    else
        # Interactive selection
        select_clients_interactive || true
    fi
fi

echo ""
echo "=== Toolchain setup complete ==="
