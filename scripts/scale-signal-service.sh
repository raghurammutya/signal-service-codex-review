#!/bin/bash
# Script to manually scale signal service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-stocksblitz-platform}"
SERVICE_NAME="signal-service"
COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.scaling.yml}"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to get current container count
get_current_count() {
    docker ps --filter "label=com.docker.compose.service=$SERVICE_NAME" --filter "label=com.docker.compose.project=$PROJECT_NAME" -q | wc -l
}

# Function to scale service
scale_service() {
    local target_count=$1
    local current_count=$(get_current_count)
    
    print_status "Current instances: $current_count"
    print_status "Target instances: $target_count"
    
    if [ "$target_count" -eq "$current_count" ]; then
        print_warning "Already at target instance count"
        return 0
    fi
    
    # Use docker-compose scale command
    print_status "Scaling $SERVICE_NAME to $target_count instances..."
    
    cd "$(dirname "$0")/.."
    docker-compose -f "$COMPOSE_FILE" up -d --scale "$SERVICE_NAME=$target_count" --no-recreate
    
    # Wait for containers to be ready
    print_status "Waiting for containers to be ready..."
    sleep 10
    
    # Verify scaling
    local new_count=$(get_current_count)
    if [ "$new_count" -eq "$target_count" ]; then
        print_status "Successfully scaled to $new_count instances"
    else
        print_error "Scaling failed. Current instances: $new_count, Target: $target_count"
        return 1
    fi
}

# Function to show usage
usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  scale <count>    Scale to specific number of instances"
    echo "  up <count>       Scale up by count"
    echo "  down <count>     Scale down by count"
    echo "  status           Show current status"
    echo "  auto             Enable auto-scaling"
    echo ""
    echo "Examples:"
    echo "  $0 scale 5       # Scale to 5 instances"
    echo "  $0 up 2          # Add 2 more instances"
    echo "  $0 down 1        # Remove 1 instance"
    echo "  $0 status        # Show current status"
}

# Function to show status
show_status() {
    local current_count=$(get_current_count)
    
    print_status "Signal Service Status"
    echo "===================="
    echo "Project: $PROJECT_NAME"
    echo "Service: $SERVICE_NAME"
    echo "Running instances: $current_count"
    echo ""
    echo "Container Details:"
    docker ps --filter "label=com.docker.compose.service=$SERVICE_NAME" --filter "label=com.docker.compose.project=$PROJECT_NAME" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    # Check orchestrator status
    echo ""
    echo "Orchestrator Status:"
    local orchestrator_running=$(docker ps --filter "label=com.docker.compose.service=signal-orchestrator" -q | wc -l)
    if [ "$orchestrator_running" -gt 0 ]; then
        echo "Auto-scaling: ENABLED"
        
        # Get scaling metrics from Redis if available
        if command -v redis-cli &> /dev/null; then
            echo ""
            echo "Recent Scaling Events:"
            redis-cli LRANGE signal:scaling:history 0 4 2>/dev/null | while read -r event; do
                echo "  $event" | jq -r '"\(.timestamp): \(.action) from \(.current) to \(.target) - \(.reason)"' 2>/dev/null || echo "  $event"
            done
        fi
    else
        echo "Auto-scaling: DISABLED"
    fi
}

# Function to enable auto-scaling
enable_auto_scaling() {
    print_status "Enabling auto-scaling..."
    
    cd "$(dirname "$0")/.."
    
    # Start orchestrator
    docker-compose -f "$COMPOSE_FILE" up -d signal-orchestrator
    
    # Verify
    sleep 5
    local orchestrator_running=$(docker ps --filter "label=com.docker.compose.service=signal-orchestrator" -q | wc -l)
    if [ "$orchestrator_running" -gt 0 ]; then
        print_status "Auto-scaling enabled successfully"
    else
        print_error "Failed to enable auto-scaling"
        return 1
    fi
}

# Main script logic
main() {
    local command=$1
    shift
    
    case "$command" in
        scale)
            if [ -z "$1" ]; then
                print_error "Please specify target instance count"
                usage
                exit 1
            fi
            scale_service "$1"
            ;;
            
        up)
            if [ -z "$1" ]; then
                print_error "Please specify number of instances to add"
                usage
                exit 1
            fi
            local current=$(get_current_count)
            local target=$((current + $1))
            scale_service "$target"
            ;;
            
        down)
            if [ -z "$1" ]; then
                print_error "Please specify number of instances to remove"
                usage
                exit 1
            fi
            local current=$(get_current_count)
            local target=$((current - $1))
            if [ "$target" -lt 1 ]; then
                print_error "Cannot scale below 1 instance"
                exit 1
            fi
            scale_service "$target"
            ;;
            
        status)
            show_status
            ;;
            
        auto)
            enable_auto_scaling
            ;;
            
        *)
            usage
            exit 1
            ;;
    esac
}

# Check if docker is available
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed or not in PATH"
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose is not installed or not in PATH"
    exit 1
fi

# Run main function
main "$@"